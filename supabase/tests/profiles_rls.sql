begin;

create extension if not exists pgtap with schema extensions;

select plan(10);

select has_table(
  'public',
  'profiles',
  'profiles table exists'
);

select columns_are(
  'public',
  'profiles',
  array['id', 'display_name', 'created_at', 'updated_at'],
  'profiles exposes the expected columns'
);

select col_is_pk(
  'public',
  'profiles',
  'id',
  'profiles.id is the primary key'
);

select ok(
  coalesce(
    (
      select c.relrowsecurity
      from pg_catalog.pg_class as c
      join pg_catalog.pg_namespace as n on n.oid = c.relnamespace
      where n.nspname = 'public' and c.relname = 'profiles'
    ),
    false
  ),
  'profiles has row level security enabled'
);

select ok(
  exists(
    select 1
    from information_schema.role_table_grants
    where table_schema = 'public'
      and table_name = 'profiles'
      and grantee = 'authenticated'
      and privilege_type = 'SELECT'
  ),
  'authenticated users can select profiles through RLS'
);

select ok(
  exists(
    select 1
    from information_schema.role_table_grants
    where table_schema = 'public'
      and table_name = 'profiles'
      and grantee = 'authenticated'
      and privilege_type = 'UPDATE'
  ),
  'authenticated users can update profiles through RLS'
);

select ok(
  exists(
    select 1
    from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename = 'profiles'
      and policyname = 'Users can view their own profile'
      and cmd = 'SELECT'
      and 'authenticated' = any(roles)
  ),
  'authenticated users have an owner-scoped select policy'
);

select ok(
  exists(
    select 1
    from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename = 'profiles'
      and policyname = 'Users can update their own profile'
      and cmd = 'UPDATE'
      and 'authenticated' = any(roles)
  ),
  'authenticated users have an owner-scoped update policy'
);

select has_function(
  'public',
  'handle_new_user',
  array[]::name[],
  'signup profile function exists'
);

select ok(
  exists(
    select 1
    from pg_catalog.pg_trigger as t
    join pg_catalog.pg_class as c on c.oid = t.tgrelid
    join pg_catalog.pg_namespace as n on n.oid = c.relnamespace
    where n.nspname = 'auth'
      and c.relname = 'users'
      and t.tgname = 'on_auth_user_created'
      and not t.tgisinternal
  ),
  'auth.users creates a profile after signup'
);

select * from finish();

rollback;
