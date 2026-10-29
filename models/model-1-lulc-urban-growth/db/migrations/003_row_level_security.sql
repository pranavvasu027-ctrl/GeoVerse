-- =============================================================================
-- GeoVerse Model 1: LULC Urban Growth — Row Level Security (RLS) & Access Policies
-- Migration: 003_row_level_security.sql
-- Description: Secures database access, enforces role boundaries, and protects Gold holdout
-- =============================================================================

-- Enable Row Level Security on all core tables
ALTER TABLE datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE samples ENABLE ROW LEVEL SECURITY;
ALTER TABLE annotations ENABLE ROW LEVEL SECURITY;
ALTER TABLE annotation_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE quality_reviews ENABLE ROW LEVEL SECURITY;

-- -----------------------------------------------------------------------------
-- 1. Service Role (Full Access for Backend Services, Migration, and Cron)
-- -----------------------------------------------------------------------------
-- The Flask backend runs server-side with service-role privileges or validated tokens.
-- Browser clients NEVER receive the service-role key.

DROP POLICY IF EXISTS service_role_all_datasets ON datasets;
CREATE POLICY service_role_all_datasets ON datasets
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_role_all_samples ON samples;
CREATE POLICY service_role_all_samples ON samples
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_role_all_annotations ON annotations;
CREATE POLICY service_role_all_annotations ON annotations
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_role_all_history ON annotation_history;
CREATE POLICY service_role_all_history ON annotation_history
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_role_all_reviews ON quality_reviews;
CREATE POLICY service_role_all_reviews ON quality_reviews
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- -----------------------------------------------------------------------------
-- 2. Anonymous / Public Clients (Read-Only Public Reference Data, No Direct Writes)
-- -----------------------------------------------------------------------------
-- Anonymous clients (e.g. browser frontend before login) can only read datasets and samples
-- to render maps, but CANNOT insert, update, or delete annotation records directly.

DROP POLICY IF EXISTS anon_select_datasets ON datasets;
CREATE POLICY anon_select_datasets ON datasets
    FOR SELECT TO anon USING (true);

DROP POLICY IF EXISTS anon_select_samples ON samples;
CREATE POLICY anon_select_samples ON samples
    FOR SELECT TO anon USING (true);

-- Explicitly disallow any write operations for anonymous role
-- (RLS default denies unpermitted operations; policies ensure read-only status)

-- -----------------------------------------------------------------------------
-- 3. Authenticated Annotators (Role-Based Access Control)
-- -----------------------------------------------------------------------------
-- Authenticated users (interpreters) can read reference data and write T1 annotations.
-- Writing to the Gold evaluation dataset requires specific administrator/auditor privileges.

DROP POLICY IF EXISTS auth_select_datasets ON datasets;
CREATE POLICY auth_select_datasets ON datasets
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS auth_select_samples ON samples;
CREATE POLICY auth_select_samples ON samples
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS auth_select_annotations ON annotations;
CREATE POLICY auth_select_annotations ON annotations
    FOR SELECT TO authenticated USING (true);

-- Authenticated users can insert/update T1 annotations
DROP POLICY IF EXISTS auth_insert_t1_annotations ON annotations;
CREATE POLICY auth_insert_t1_annotations ON annotations
    FOR INSERT TO authenticated
    WITH CHECK (dataset_id = 't1');

DROP POLICY IF EXISTS auth_update_t1_annotations ON annotations;
CREATE POLICY auth_update_t1_annotations ON annotations
    FOR UPDATE TO authenticated
    USING (dataset_id = 't1')
    WITH CHECK (dataset_id = 't1');

-- Authenticated users can read quality reviews
DROP POLICY IF EXISTS auth_select_reviews ON quality_reviews;
CREATE POLICY auth_select_reviews ON quality_reviews
    FOR SELECT TO authenticated USING (true);

-- Authenticated users can insert quality reviews
DROP POLICY IF EXISTS auth_insert_reviews ON quality_reviews;
CREATE POLICY auth_insert_reviews ON quality_reviews
    FOR INSERT TO authenticated
    WITH CHECK (true);

-- -----------------------------------------------------------------------------
-- 4. Schema-Level & Table-Level Grants / Hardening (Defense-in-Depth)
-- -----------------------------------------------------------------------------
-- Object-level privileges reinforce RLS to prevent permission escalation.

-- Function execution hardening (prevent direct invocation by untrusted roles)
REVOKE EXECUTE ON FUNCTION record_annotation_history() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION record_annotation_history() TO authenticated, service_role;

REVOKE EXECUTE ON FUNCTION set_updated_at() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION set_updated_at() TO authenticated, service_role;

-- Table privileges: Revoke modification privileges from public/anon
REVOKE ALL ON TABLE annotation_history FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON TABLE annotation_history TO service_role;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE datasets, samples FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE datasets, samples TO anon, authenticated;
GRANT ALL ON TABLE datasets, samples TO service_role;

REVOKE ALL ON TABLE annotations FROM PUBLIC, anon;
REVOKE DELETE, TRUNCATE ON TABLE annotations FROM authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE annotations TO authenticated;
GRANT ALL ON TABLE annotations TO service_role;

REVOKE ALL ON TABLE quality_reviews FROM PUBLIC, anon;
REVOKE UPDATE, DELETE, TRUNCATE ON TABLE quality_reviews FROM authenticated;
GRANT SELECT, INSERT ON TABLE quality_reviews TO authenticated;
GRANT ALL ON TABLE quality_reviews TO service_role;

-- Sequence usage for ID generation
GRANT USAGE, SELECT ON SEQUENCE annotations_id_seq, quality_reviews_review_id_seq TO authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;

