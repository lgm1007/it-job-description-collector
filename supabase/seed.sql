-- Local development only: `supabase start` and `supabase db reset` run this file, `supabase db push`
-- does not, so this account never reaches the real project. Sign in at http://127.0.0.1:3000 with it.
insert into auth.users (
  instance_id, id, aud, role, email, encrypted_password, email_confirmed_at, created_at, updated_at,
  raw_app_meta_data, raw_user_meta_data, confirmation_token, recovery_token, email_change_token_new, email_change
) values (
  '00000000-0000-0000-0000-000000000000', 'a0000000-0000-4000-8000-000000000001', 'authenticated', 'authenticated',
  'dev@example.test', extensions.crypt('local-dev-only', extensions.gen_salt('bf')), now(), now(), now(),
  '{"provider": "email", "providers": ["email"]}', '{}', '', '', '', ''
);
insert into auth.identities (id, user_id, provider, provider_id, identity_data, last_sign_in_at, created_at, updated_at)
values (
  'a0000000-0000-4000-8000-000000000002', 'a0000000-0000-4000-8000-000000000001', 'email',
  'a0000000-0000-4000-8000-000000000001',
  '{"sub": "a0000000-0000-4000-8000-000000000001", "email": "dev@example.test", "email_verified": true}',
  now(), now(), now()
);
insert into private.viewers (user_id) values ('a0000000-0000-4000-8000-000000000001');
