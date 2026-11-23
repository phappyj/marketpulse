-- ==========================================================================
-- 예측판 (YECHEUKPAN) — 조회수(클릭수) 기능
-- 2026-11-24 · Supabase SQL Editor에서 실행 (재실행해도 안전)
--
-- 1) 자유 수다방 글: yp_posts.views (실제 클릭 시 1 증가, 목록·상세에 표시)
-- 2) 이슈 카드: yp_issue_views (카드를 열 때 1 증가, 카드·상세에 표시)
-- 3) 같은 브라우저(yp_cid)에서 같은 글/이슈는 '하루 1회'만 카운트
--    → 새로고침·연타로 숫자가 부풀지 않습니다. 초기값은 0부터 시작합니다.
-- ==========================================================================

-- ---------- 1. 컬럼·테이블 ----------
alter table public.yp_posts add column if not exists views bigint not null default 0;

create table if not exists public.yp_issue_views (
  issue_key  text primary key,
  views      bigint not null default 0,
  updated_at timestamptz not null default now()
);

create table if not exists public.yp_view_marks (
  id         bigserial primary key,
  kind       text not null check (kind in ('post','issue')),
  target_key text not null,
  viewer_id  text not null,
  view_day   date not null default ((now() at time zone 'Asia/Seoul')::date),
  created_at timestamptz not null default now(),
  unique (kind, target_key, viewer_id, view_day)
);
create index if not exists yp_view_marks_day_idx on public.yp_view_marks (view_day);

alter table public.yp_issue_views enable row level security;
alter table public.yp_view_marks  enable row level security;
revoke all on public.yp_issue_views from anon, authenticated;
revoke all on public.yp_view_marks  from anon, authenticated;

-- ---------- 2. 조회수 집계 RPC ----------
create or replace function public.yp_track_view(p_kind text, p_key text, p_viewer text)
returns jsonb
language plpgsql security definer set search_path = public, pg_temp
as $$
declare
  v_views bigint;
  v_counted boolean := false;
  v_ins int := 0;
  v_pid bigint;
  v_viewer text;
begin
  if p_kind is null or p_kind not in ('post','issue') then raise exception 'bad_kind'; end if;
  if p_key is null or char_length(p_key) < 1 or char_length(p_key) > 128 then
    raise exception 'bad_target';
  end if;

  v_viewer := nullif(btrim(coalesce(p_viewer, '')), '');
  if v_viewer is not null and (char_length(v_viewer) < 6 or char_length(v_viewer) > 64) then
    raise exception 'client_required';
  end if;

  if p_kind = 'post' then
    if p_key !~ '^[0-9]{1,18}$' then raise exception 'bad_target'; end if;
    v_pid := p_key::bigint;
    if not exists (
      select 1 from public.yp_posts
       where id = v_pid and not hidden and report_count < 3
    ) then
      raise exception 'post_not_found';
    end if;
  end if;

  if v_viewer is null then
    v_counted := true;                       -- 브라우저 식별값이 없으면 그냥 집계
  else
    insert into public.yp_view_marks (kind, target_key, viewer_id)
    values (p_kind, p_key, v_viewer)
    on conflict (kind, target_key, viewer_id, view_day) do nothing;
    get diagnostics v_ins = row_count;
    v_counted := (v_ins = 1);
  end if;

  if p_kind = 'post' then
    if v_counted then
      update public.yp_posts set views = views + 1 where id = v_pid returning views into v_views;
    else
      select views into v_views from public.yp_posts where id = v_pid;
    end if;
  else
    if v_counted then
      insert into public.yp_issue_views (issue_key, views) values (p_key, 1)
      on conflict (issue_key) do update
         set views = public.yp_issue_views.views + 1,
             updated_at = now()
      returning views into v_views;
    else
      select views into v_views from public.yp_issue_views where issue_key = p_key;
    end if;
  end if;

  return jsonb_build_object('ok', true, 'views', coalesce(v_views, 0), 'counted', v_counted);
end $$;

create or replace function public.yp_issue_view_counts(p_keys text[] default null)
returns table (issue_key text, views bigint)
language sql stable security definer set search_path = public, pg_temp
as $$
  select v.issue_key, v.views
  from public.yp_issue_views v
  where p_keys is null or v.issue_key = any(p_keys);
$$;

-- ---------- 3. 목록·상세에 조회수 포함 ----------
drop function if exists public.yp_list_posts(text, int);

create or replace function public.yp_list_posts(p_category text default 'all', p_limit int default 60)
returns table (
  id bigint, category text, title text, nickname text,
  created_at timestamptz, comment_count bigint, views bigint
)
language sql stable security definer set search_path = public, pg_temp
as $$
  select p.id, p.category, p.title, p.nickname, p.created_at,
         (select count(*) from public.yp_comments c
           where c.post_id = p.id and not c.hidden and c.report_count < 3) as comment_count,
         coalesce(p.views, 0) as views
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
           'nickname', p.nickname, 'created_at', p.created_at,
           'views', coalesce(p.views, 0))
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

-- ---------- 4. 실행 권한 ----------
grant execute on function
  public.yp_track_view(text, text, text),
  public.yp_issue_view_counts(text[]),
  public.yp_list_posts(text, int)
to anon, authenticated;

notify pgrst, 'reload schema';
