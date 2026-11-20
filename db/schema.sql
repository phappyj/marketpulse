-- ==========================================================================
-- 예측판 (YECHEUKPAN) — 커뮤니티 스키마
-- Supabase SQL Editor에서 한 번 실행합니다. (재실행해도 안전하게 작성)
-- 테이블은 모두 yp_ 접두어로 분리되어 있고, 쓰기는 전부 SECURITY DEFINER
-- RPC를 통해서만 허용합니다. (비밀번호 해시는 클라이언트로 나가지 않음)
-- ==========================================================================

create extension if not exists pgcrypto with schema extensions;

-- ---------- 1. 테이블 ----------
create table if not exists public.yp_posts (
  id           bigserial primary key,
  category     text not null default 'free'
               check (category in ('rate','coin','ai','free')),
  title        text not null,
  body         text not null,
  nickname     text not null,
  pw_hash      text not null,
  report_count integer not null default 0,
  hidden       boolean not null default false,
  client_id    text,
  created_at   timestamptz not null default now()
);

create table if not exists public.yp_comments (
  id           bigserial primary key,
  issue_key    text,
  post_id      bigint references public.yp_posts(id) on delete cascade,
  nickname     text not null,
  pw_hash      text not null,
  body         text not null,
  report_count integer not null default 0,
  hidden       boolean not null default false,
  client_id    text,
  created_at   timestamptz not null default now(),
  constraint yp_comments_target check ((issue_key is null) <> (post_id is null))
);
create index if not exists yp_comments_issue_idx on public.yp_comments (issue_key);
create index if not exists yp_comments_post_idx  on public.yp_comments (post_id);

create table if not exists public.yp_votes (
  id         bigserial primary key,
  issue_key  text not null,
  choice     text not null check (choice in ('yes','no')),
  voter_id   text not null,
  created_at timestamptz not null default now(),
  unique (issue_key, voter_id)
);

create table if not exists public.yp_reports (
  id          bigserial primary key,
  target_kind text not null check (target_kind in ('post','comment')),
  target_id   bigint not null,
  reporter_id text not null,
  created_at  timestamptz not null default now(),
  unique (target_kind, target_id, reporter_id)
);

create table if not exists public.yp_banned_words (
  id   serial primary key,
  word text not null unique
);

-- 기본 금칙어 (필요하면 추가/삭제)
insert into public.yp_banned_words (word) values
  ('토토'), ('사설토토'), ('배팅사이트'), ('먹튀'), ('바카라'), ('카지노'),
  ('슬롯'), ('파워볼'), ('스포츠토토'), ('프로토'), ('온라인카지노'),
  ('레퍼럴'), ('추천인'), ('리퍼럴'), ('수익인증'), ('리딩방'), ('텔레그램'),
  ('오픈채팅'), ('카톡주세요'), ('카톡문의'), ('디엠주세요'), ('대리입금'),
  ('환전'), ('선입금'), ('고정수익'), ('원금보장'), ('100%수익'), ('폭리'),
  ('씨발'), ('시발'), ('ㅅㅂ'), ('병신'), ('븅신'), ('좆'), ('지랄'), ('염병'),
  ('미친놈'), ('미친년'), ('개새끼'), ('새끼'), ('닥쳐'), ('꺼져')
on conflict (word) do nothing;

-- ---------- 2. RLS ----------
alter table public.yp_posts        enable row level security;
alter table public.yp_comments     enable row level security;
alter table public.yp_votes        enable row level security;
alter table public.yp_reports      enable row level security;
alter table public.yp_banned_words enable row level security;

drop policy if exists yp_posts_read on public.yp_posts;
create policy yp_posts_read on public.yp_posts
  for select to anon, authenticated using (hidden = false and report_count < 3);

drop policy if exists yp_comments_read on public.yp_comments;
create policy yp_comments_read on public.yp_comments
  for select to anon, authenticated using (hidden = false and report_count < 3);

drop policy if exists yp_votes_read on public.yp_votes;
create policy yp_votes_read on public.yp_votes
  for select to anon, authenticated using (true);

-- posts / comments 는 읽기 전용 컬럼만 부여(pw_hash 차단), 쓰기는 RPC만
revoke all on public.yp_posts    from anon, authenticated;
revoke all on public.yp_comments from anon, authenticated;
revoke all on public.yp_votes    from anon, authenticated;
revoke all on public.yp_reports  from anon, authenticated;
revoke all on public.yp_banned_words from anon, authenticated;

grant select (id, category, title, body, nickname, report_count, hidden, created_at)
  on public.yp_posts to anon, authenticated;
grant select (id, issue_key, post_id, nickname, body, report_count, hidden, created_at)
  on public.yp_comments to anon, authenticated;
grant select on public.yp_votes to anon, authenticated;

grant usage, select on all sequences in schema public to anon, authenticated;

-- ---------- 3. 검증 도우미 ----------
create or replace function public.yp_nick(p_text text)
returns text
language plpgsql immutable
as $$
declare t text;
begin
  t := btrim(regexp_replace(coalesce(p_text, ''), '\s+', ' ', 'g'));
  if char_length(t) < 1 then raise exception 'nickname_required'; end if;
  if char_length(t) > 16 then raise exception 'nickname_too_long'; end if;
  return t;
end $$;

create or replace function public.yp_text(p_text text, p_max int)
returns text
language plpgsql immutable
as $$
declare t text;
begin
  t := btrim(regexp_replace(coalesce(p_text, ''), '[ \t]+', ' ', 'g'));
  t := regexp_replace(t, '\n{3,}', E'\n\n', 'g');
  if char_length(t) < 1 then raise exception 'text_required'; end if;
  if char_length(t) > p_max then raise exception 'text_too_long'; end if;
  return t;
end $$;

create or replace function public.yp_banned(p_text text)
returns boolean
language sql stable security definer set search_path = public, pg_temp
as $$
  select exists (
    select 1 from public.yp_banned_words w
    where char_length(w.word) > 0
      and position(lower(w.word) in lower(coalesce(p_text, ''))) > 0
  );
$$;

-- 연속 작성 제한: 같은 client_id로 15초 이내 재작성 금지
create or replace function public.yp_cooldown(p_table text, p_client text)
returns void
language plpgsql security definer set search_path = public, pg_temp
as $$
declare v_last timestamptz; v_hour int;
begin
  if p_client is null or char_length(p_client) < 6 then
    raise exception 'client_required';
  end if;

  if p_table = 'posts' then
    select max(created_at) into v_last from public.yp_posts
      where client_id = p_client;
    select count(*) into v_hour from public.yp_posts
      where client_id = p_client and created_at > now() - interval '1 hour';
  else
    select max(created_at) into v_last from public.yp_comments
      where client_id = p_client;
    select count(*) into v_hour from public.yp_comments
      where client_id = p_client and created_at > now() - interval '1 hour';
  end if;

  if v_last is not null and v_last > now() - interval '15 seconds' then
    raise exception 'cooldown';
  end if;
  if v_hour >= 30 then
    raise exception 'rate_limited';
  end if;
end $$;

-- ---------- 4. 투표 ----------
create or replace function public.yp_vote(p_issue_key text, p_choice text, p_voter text)
returns jsonb
language plpgsql security definer set search_path = public, pg_temp
as $$
declare v_yes bigint; v_no bigint; v_choice text;
begin
  if p_issue_key is null or char_length(p_issue_key) < 2 or char_length(p_issue_key) > 64 then
    raise exception 'bad_issue';
  end if;
  if p_choice not in ('yes','no') then raise exception 'bad_choice'; end if;
  if p_voter is null or char_length(p_voter) < 6 or char_length(p_voter) > 64 then
    raise exception 'client_required';
  end if;

  insert into public.yp_votes (issue_key, choice, voter_id)
  values (p_issue_key, p_choice, p_voter)
  on conflict (issue_key, voter_id) do nothing;

  select choice into v_choice from public.yp_votes
    where issue_key = p_issue_key and voter_id = p_voter;

  select count(*) filter (where choice = 'yes'),
         count(*) filter (where choice = 'no')
    into v_yes, v_no
    from public.yp_votes where issue_key = p_issue_key;

  return jsonb_build_object('ok', true, 'my', v_choice, 'yes', v_yes, 'no', v_no);
end $$;

create or replace function public.yp_vote_tally(p_keys text[] default null)
returns table (issue_key text, yes bigint, no bigint)
language sql stable security definer set search_path = public, pg_temp
as $$
  select v.issue_key,
         count(*) filter (where v.choice = 'yes') as yes,
         count(*) filter (where v.choice = 'no')  as no
  from public.yp_votes v
  where p_keys is null or v.issue_key = any(p_keys)
  group by v.issue_key;
$$;

create or replace function public.yp_my_votes(p_voter text)
returns table (issue_key text, choice text)
language sql stable security definer set search_path = public, pg_temp
as $$
  select issue_key, choice from public.yp_votes where voter_id = p_voter;
$$;

-- ---------- 5. 댓글 ----------
create or replace function public.yp_add_issue_comment(
  p_issue_key text, p_nickname text, p_pw text, p_body text, p_client text
)
returns jsonb
language plpgsql security definer set search_path = public, pg_temp
as $$
declare v_id bigint; v_nick text; v_body text;
begin
  if p_issue_key is null or char_length(p_issue_key) > 64 then raise exception 'bad_issue'; end if;
  if p_pw !~ '^[0-9]{4}$' then raise exception 'bad_pw'; end if;
  v_nick := public.yp_nick(p_nickname);
  v_body := public.yp_text(p_body, 600);
  if public.yp_banned(v_nick || ' ' || v_body) then raise exception 'banned'; end if;
  perform public.yp_cooldown('comments', p_client);

  insert into public.yp_comments (issue_key, nickname, pw_hash, body, client_id)
  values (p_issue_key, v_nick, extensions.crypt(p_pw, extensions.gen_salt('bf')), v_body, p_client)
  returning id into v_id;

  return jsonb_build_object('ok', true, 'id', v_id);
end $$;

create or replace function public.yp_add_post_comment(
  p_post_id bigint, p_nickname text, p_pw text, p_body text, p_client text
)
returns jsonb
language plpgsql security definer set search_path = public, pg_temp
as $$
declare v_id bigint; v_nick text; v_body text;
begin
  if not exists (select 1 from public.yp_posts where id = p_post_id and not hidden) then
    raise exception 'post_not_found';
  end if;
  if p_pw !~ '^[0-9]{4}$' then raise exception 'bad_pw'; end if;
  v_nick := public.yp_nick(p_nickname);
  v_body := public.yp_text(p_body, 600);
  if public.yp_banned(v_nick || ' ' || v_body) then raise exception 'banned'; end if;
  perform public.yp_cooldown('comments', p_client);

  insert into public.yp_comments (post_id, nickname, pw_hash, body, client_id)
  values (p_post_id, v_nick, extensions.crypt(p_pw, extensions.gen_salt('bf')), v_body, p_client)
  returning id into v_id;

  return jsonb_build_object('ok', true, 'id', v_id);
end $$;

create or replace function public.yp_issue_comments(p_issue_key text)
returns table (id bigint, nickname text, body text, created_at timestamptz)
language sql stable security definer set search_path = public, pg_temp
as $$
  select c.id, c.nickname, c.body, c.created_at
  from public.yp_comments c
  where c.issue_key = p_issue_key and not c.hidden and c.report_count < 3
  order by c.created_at asc
  limit 200;
$$;

create or replace function public.yp_comment_counts(p_keys text[])
returns table (issue_key text, n bigint)
language sql stable security definer set search_path = public, pg_temp
as $$
  select c.issue_key, count(*)
  from public.yp_comments c
  where c.issue_key = any(p_keys) and not c.hidden and c.report_count < 3
  group by c.issue_key;
$$;

-- ---------- 6. 자유 수다방 ----------
create or replace function public.yp_add_post(
  p_category text, p_title text, p_body text, p_nickname text, p_pw text, p_client text
)
returns jsonb
language plpgsql security definer set search_path = public, pg_temp
as $$
declare v_id bigint; v_nick text; v_title text; v_body text; v_cat text;
begin
  v_cat := coalesce(nullif(p_category, ''), 'free');
  if v_cat not in ('rate','coin','ai','free') then raise exception 'bad_category'; end if;
  if p_pw !~ '^[0-9]{4}$' then raise exception 'bad_pw'; end if;
  v_nick  := public.yp_nick(p_nickname);
  v_title := public.yp_text(p_title, 80);
  v_body  := public.yp_text(p_body, 4000);
  if public.yp_banned(v_nick || ' ' || v_title || ' ' || v_body) then raise exception 'banned'; end if;
  perform public.yp_cooldown('posts', p_client);

  insert into public.yp_posts (category, title, body, nickname, pw_hash, client_id)
  values (v_cat, v_title, v_body, v_nick, extensions.crypt(p_pw, extensions.gen_salt('bf')), p_client)
  returning id into v_id;

  return jsonb_build_object('ok', true, 'id', v_id);
end $$;

create or replace function public.yp_list_posts(p_category text default 'all', p_limit int default 60)
returns table (
  id bigint, category text, title text, nickname text,
  created_at timestamptz, comment_count bigint
)
language sql stable security definer set search_path = public, pg_temp
as $$
  select p.id, p.category, p.title, p.nickname, p.created_at,
         (select count(*) from public.yp_comments c
           where c.post_id = p.id and not c.hidden and c.report_count < 3) as comment_count
  from public.yp_posts p
  where not p.hidden and p.report_count < 3
    and (coalesce(p_category,'all') = 'all' or p.category = p_category)
  order by p.created_at desc
  limit least(coalesce(p_limit, 60), 100);
$$;

create or replace function public.yp_get_post(p_id bigint)
returns jsonb
language plpgsql stable security definer set search_path = public, pg_temp
as $$
declare v_post jsonb; v_comments jsonb;
begin
  select jsonb_build_object(
           'id', p.id, 'category', p.category, 'title', p.title, 'body', p.body,
           'nickname', p.nickname, 'created_at', p.created_at)
    into v_post
    from public.yp_posts p
   where p.id = p_id and not p.hidden and p.report_count < 3;

  if v_post is null then return null; end if;

  select coalesce(jsonb_agg(jsonb_build_object(
           'id', c.id, 'nickname', c.nickname, 'body', c.body, 'created_at', c.created_at
         ) order by c.created_at asc), '[]'::jsonb)
    into v_comments
    from public.yp_comments c
   where c.post_id = p_id and not c.hidden and c.report_count < 3;

  return jsonb_build_object('post', v_post, 'comments', v_comments);
end $$;

-- ---------- 7. 삭제 (비밀번호 검증) ----------
create or replace function public.yp_delete_comment(p_id bigint, p_pw text)
returns jsonb
language plpgsql security definer set search_path = public, pg_temp
as $$
declare v_hash text;
begin
  select pw_hash into v_hash from public.yp_comments where id = p_id;
  if v_hash is null then raise exception 'not_found'; end if;
  if p_pw !~ '^[0-9]{4}$' then raise exception 'bad_pw'; end if;
  if v_hash <> extensions.crypt(p_pw, v_hash) then raise exception 'wrong_pw'; end if;
  delete from public.yp_comments where id = p_id;
  return jsonb_build_object('ok', true);
end $$;

create or replace function public.yp_delete_post(p_id bigint, p_pw text)
returns jsonb
language plpgsql security definer set search_path = public, pg_temp
as $$
declare v_hash text; v_client text;
begin
  select pw_hash, client_id into v_hash, v_client from public.yp_posts where id = p_id;
  if v_hash is null then raise exception 'not_found'; end if;
  if v_client = 'system-notice' then raise exception 'protected_post'; end if;
  if p_pw !~ '^[0-9]{4}$' then raise exception 'bad_pw'; end if;
  if v_hash <> extensions.crypt(p_pw, v_hash) then raise exception 'wrong_pw'; end if;
  delete from public.yp_posts where id = p_id;
  return jsonb_build_object('ok', true);
end $$;

-- ---------- 8. 신고 ----------
create or replace function public.yp_report(p_kind text, p_id bigint, p_reporter text)
returns jsonb
language plpgsql security definer set search_path = public, pg_temp
as $$
declare v_inserted int := 0; v_count int;
begin
  if p_kind not in ('post','comment') then raise exception 'bad_kind'; end if;
  if p_reporter is null or char_length(p_reporter) < 6 then raise exception 'client_required'; end if;

  insert into public.yp_reports (target_kind, target_id, reporter_id)
  values (p_kind, p_id, p_reporter)
  on conflict (target_kind, target_id, reporter_id) do nothing;
  get diagnostics v_inserted = row_count;

  if v_inserted = 1 then
    if p_kind = 'post' then
      update public.yp_posts set report_count = report_count + 1,
             hidden = (report_count + 1) >= 3
       where id = p_id returning report_count into v_count;
    else
      update public.yp_comments set report_count = report_count + 1,
             hidden = (report_count + 1) >= 3
       where id = p_id returning report_count into v_count;
    end if;
  end if;

  return jsonb_build_object('ok', true, 'reported', v_inserted = 1, 'report_count', coalesce(v_count, 0));
end $$;

-- ---------- 9. 실행 권한 ----------
grant execute on function
  public.yp_vote(text, text, text),
  public.yp_vote_tally(text[]),
  public.yp_my_votes(text),
  public.yp_add_issue_comment(text, text, text, text, text),
  public.yp_add_post_comment(bigint, text, text, text, text),
  public.yp_issue_comments(text),
  public.yp_comment_counts(text[]),
  public.yp_add_post(text, text, text, text, text, text),
  public.yp_list_posts(text, int),
  public.yp_get_post(bigint),
  public.yp_delete_comment(bigint, text),
  public.yp_delete_post(bigint, text),
  public.yp_report(text, bigint, text),
  public.yp_banned(text)
to anon, authenticated;

revoke execute on function public.yp_cooldown(text, text) from anon, authenticated;

-- ---------- 10. 중계 수다방 안내글 1건 ----------
insert into public.yp_posts (category, title, body, nickname, pw_hash, client_id)
select 'free',
       '예측판 수다방 이용 안내',
       E'예측판(예추크판)에 오신 것을 환영합니다.\n\n· 이곳은 금리·증시, 코인, AI·빅테크, 그리고 잡담을 나누는 자유 수다방입니다.\n· 회원가입 없이 닉네임과 4자리 비밀번호만으로 글과 댓글을 남길 수 있습니다. 같은 비밀번호로 직접 삭제할 수 있어요.\n· 베팅·도박·사설 토토, 투자 리딩방, 텔레그램·레퍼럴 홍보 글은 금칙어 필터로 자동 차단됩니다.\n· 욕설과 혐오 표현, 광고는 신고 버튼으로 알려 주세요. 신고 3회가 쌓이면 자동으로 가려집니다.\n· 모든 내용은 정보 공유 목적이며, 투자 권유나 매수·매도 신호가 아닙니다. 판단과 책임은 본인에게 있습니다.',
       '예측판',
       extensions.crypt('2026', extensions.gen_salt('bf')),
       'system-notice'
where not exists (
  select 1 from public.yp_posts where client_id = 'system-notice'
);
