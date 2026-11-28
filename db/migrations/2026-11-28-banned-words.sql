-- 2026-11-28 간판 리브랜딩에 맞춘 금칙어 보강
-- 접속 우회·가입 유도·입금 안내 문구를 커뮤니티에서 차단한다(해외 거래소 관련 법적 안전선).
-- Supabase 대시보드 → SQL Editor 에서 그대로 실행하면 된다. 여러 번 실행해도 안전하다.
insert into public.yp_banned_words (word) values
  ('VPN'), ('우회'), ('가입링크'), ('추천인코드'), ('초대코드'),
  ('입금방법'), ('지갑연결'), ('배당'), ('픽공유'), ('텔레그램방')
on conflict (word) do nothing;

-- 확인
-- select word from public.yp_banned_words
--  where word in ('VPN','우회','가입링크','추천인코드','초대코드','입금방법','지갑연결','배당','픽공유','텔레그램방')
--  order by word;
