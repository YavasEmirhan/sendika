-- Yerel geliştirme için roller. Üretimde parolalar gizli değişkenlerden gelmelidir.
CREATE ROLE hk_owner LOGIN PASSWORD 'owner_dev_pw';
CREATE ROLE hk_app LOGIN PASSWORD 'app_dev_pw' NOSUPERUSER NOBYPASSRLS;
CREATE DATABASE hakkopru OWNER hk_owner;
CREATE DATABASE hakkopru_test OWNER hk_owner;
