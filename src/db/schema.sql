-- FeedForward Database Schema
-- Generated from live database. See migrations/ for incremental changes.
--
-- PostgreSQL 14+
-- Requires: pgvector extension for embeddings

--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: update_research_embeddings_timestamp(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_research_embeddings_timestamp() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: update_stories_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_stories_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: context_usage_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.context_usage_logs (
    id integer NOT NULL,
    theme_id integer,
    conversation_id text NOT NULL,
    pipeline_run_id integer,
    context_used jsonb DEFAULT '[]'::jsonb,
    context_gaps jsonb DEFAULT '[]'::jsonb,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: TABLE context_usage_logs; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.context_usage_logs IS 'Tracks product context usage during theme extraction for optimization (Issue #144)';


--
-- Name: COLUMN context_usage_logs.context_used; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.context_usage_logs.context_used IS 'Product doc sections used in analysis';


--
-- Name: COLUMN context_usage_logs.context_gaps; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.context_usage_logs.context_gaps IS 'Missing context hints for future improvement';


--
-- Name: context_usage_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.context_usage_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: context_usage_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.context_usage_logs_id_seq OWNED BY public.context_usage_logs.id;


--
-- Name: conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversations (
    id text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    classified_at timestamp with time zone DEFAULT now(),
    source_body text,
    source_type text,
    source_subject text,
    contact_email text,
    contact_id text,
    issue_type text NOT NULL,
    sentiment text NOT NULL,
    churn_risk boolean DEFAULT false NOT NULL,
    priority text NOT NULL,
    classifier_version text DEFAULT 'v1'::text,
    raw_response jsonb,
    user_id text,
    org_id text,
    stage1_type character varying(50),
    stage1_confidence character varying(20),
    stage1_routing_priority character varying(20),
    stage1_urgency character varying(20),
    stage1_auto_response_eligible boolean DEFAULT false,
    stage1_routing_team character varying(50),
    stage2_type character varying(50),
    stage2_confidence character varying(20),
    classification_changed boolean DEFAULT false,
    disambiguation_level character varying(20),
    stage2_reasoning text,
    has_support_response boolean DEFAULT false,
    support_response_count integer DEFAULT 0,
    source_url text,
    resolution_action character varying(100),
    resolution_detected boolean DEFAULT false,
    support_insights jsonb,
    story_id text,
    data_source character varying(50) DEFAULT 'intercom'::character varying,
    source_metadata jsonb,
    pipeline_run_id integer,
    CONSTRAINT conversations_issue_type_check CHECK ((issue_type = ANY (ARRAY['bug_report'::text, 'feature_request'::text, 'product_question'::text, 'plan_question'::text, 'marketing_question'::text, 'billing'::text, 'account_access'::text, 'feedback'::text, 'other'::text]))),
    CONSTRAINT conversations_priority_check CHECK ((priority = ANY (ARRAY['urgent'::text, 'high'::text, 'normal'::text, 'low'::text]))),
    CONSTRAINT conversations_sentiment_check CHECK ((sentiment = ANY (ARRAY['frustrated'::text, 'neutral'::text, 'satisfied'::text])))
);


--
-- Name: COLUMN conversations.stage1_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conversations.stage1_type IS 'Fast routing classification (8 types: product_issue, how_to_question, feature_request, account_issue, billing_question, configuration_help, general_inquiry, spam)';


--
-- Name: COLUMN conversations.stage2_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conversations.stage2_type IS 'Refined classification with full conversation context';


--
-- Name: COLUMN conversations.classification_changed; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conversations.classification_changed IS 'TRUE if Stage 2 classification differs from Stage 1';


--
-- Name: COLUMN conversations.disambiguation_level; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conversations.disambiguation_level IS 'How much support clarified vague customer message (high, medium, low, none)';


--
-- Name: COLUMN conversations.support_insights; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conversations.support_insights IS 'Extracted insights: {issue_confirmed, root_cause, solution_type, products_mentioned, features_mentioned}';


--
-- Name: COLUMN conversations.story_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conversations.story_id IS 'Shortcut story/ticket ID that this conversation is linked to. Multiple conversations may share the same story_id, providing ground truth clustering for categorization validation.';


--
-- Name: COLUMN conversations.data_source; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conversations.data_source IS 'Source of the conversation: intercom, coda, etc.';


--
-- Name: COLUMN conversations.source_metadata; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conversations.source_metadata IS 'Source-specific metadata (page_id, participant, etc.)';


--
-- Name: COLUMN conversations.pipeline_run_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conversations.pipeline_run_id IS 'Pipeline run that classified this conversation. NULL for pre-migration data (uses timestamp fallback). Replaces timestamp heuristics for accurate run scoping.';


--
-- Name: themes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.themes (
    id integer NOT NULL,
    conversation_id text NOT NULL,
    product_area text NOT NULL,
    component text NOT NULL,
    issue_signature text NOT NULL,
    user_intent text,
    symptoms jsonb,
    affected_flow text,
    root_cause_hypothesis text,
    extracted_at timestamp with time zone DEFAULT now(),
    extractor_version text DEFAULT 'v1'::text,
    data_source character varying(50) DEFAULT 'intercom'::character varying,
    pipeline_run_id integer,
    quality_score real,
    quality_details jsonb,
    component_raw text,
    product_area_raw text,
    component_raw_inferred boolean DEFAULT false,
    diagnostic_summary text,
    key_excerpts jsonb DEFAULT '[]'::jsonb,
    resolution_action character varying(50),
    root_cause text,
    solution_provided text,
    resolution_category character varying(50)
);


--
-- Name: COLUMN themes.data_source; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.themes.data_source IS 'Source of the theme: intercom, coda, etc.';


--
-- Name: COLUMN themes.quality_score; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.themes.quality_score IS 'Composite quality score 0.0-1.0 from vocabulary match + confidence';


--
-- Name: COLUMN themes.quality_details; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.themes.quality_details IS 'Breakdown of quality gate checks: vocabulary_match, confidence, etc.';


--
-- Name: COLUMN themes.diagnostic_summary; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.themes.diagnostic_summary IS 'LLM-generated 2-4 sentence summary for developers (Issue #144)';


--
-- Name: COLUMN themes.key_excerpts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.themes.key_excerpts IS 'Key conversation excerpts: [{text, relevance}] (Issue #144)';


--
-- Name: COLUMN themes.resolution_action; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.themes.resolution_action IS 'LLM-detected support action: escalated_to_engineering, provided_workaround, user_education, manual_intervention, no_resolution (Issue #146)';


--
-- Name: COLUMN themes.root_cause; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.themes.root_cause IS 'LLM hypothesis for root cause - 1 sentence (Issue #146)';


--
-- Name: COLUMN themes.solution_provided; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.themes.solution_provided IS 'Solution given by support - 1-2 sentences (Issue #146)';


--
-- Name: COLUMN themes.resolution_category; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.themes.resolution_category IS 'Category for analytics: escalation, workaround, education, self_service_gap, unresolved (Issue #146)';


--
-- Name: conversation_clusters; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.conversation_clusters AS
 SELECT c.story_id,
    count(*) AS conversation_count,
    array_agg(c.id ORDER BY c.created_at) AS conversation_ids,
    min(c.created_at) AS first_conversation_at,
    max(c.created_at) AS last_conversation_at,
    array_agg(DISTINCT c.issue_type) AS issue_types,
    ( SELECT array_agg(DISTINCT t.product_area) AS array_agg
           FROM public.themes t
          WHERE (t.conversation_id = ANY (array_agg(c.id)))) AS product_areas,
    ( SELECT array_agg(DISTINCT t.issue_signature) AS array_agg
           FROM public.themes t
          WHERE (t.conversation_id = ANY (array_agg(c.id)))) AS issue_signatures
   FROM public.conversations c
  WHERE (c.story_id IS NOT NULL)
  GROUP BY c.story_id
 HAVING (count(*) >= 2)
  ORDER BY (count(*)) DESC;


--
-- Name: VIEW conversation_clusters; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON VIEW public.conversation_clusters IS 'Groups conversations by Shortcut story_id to analyze clustering patterns and categorization consistency.';


--
-- Name: conversation_embeddings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversation_embeddings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    conversation_id character varying(255) NOT NULL,
    pipeline_run_id integer,
    embedding public.vector(1536) NOT NULL,
    model_version character varying(50) DEFAULT 'text-embedding-3-small'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: TABLE conversation_embeddings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.conversation_embeddings IS 'Vector embeddings for conversation semantic clustering (T-006 hybrid approach)';


--
-- Name: COLUMN conversation_embeddings.conversation_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conversation_embeddings.conversation_id IS 'References conversations.id';


--
-- Name: COLUMN conversation_embeddings.pipeline_run_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conversation_embeddings.pipeline_run_id IS 'Run scoping per T-004 - links to pipeline_runs.id';


--
-- Name: COLUMN conversation_embeddings.embedding; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conversation_embeddings.embedding IS 'OpenAI text-embedding-3-small vector (1536 dims)';


--
-- Name: conversation_facet; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversation_facet (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    conversation_id character varying(255) NOT NULL,
    pipeline_run_id integer,
    action_type character varying(20) NOT NULL,
    direction character varying(15) NOT NULL,
    symptom character varying(200),
    user_goal character varying(200),
    model_version character varying(50) DEFAULT 'gpt-4o-mini'::character varying NOT NULL,
    extraction_confidence character varying(10),
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: TABLE conversation_facet; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.conversation_facet IS 'Extracted facets for fine-grained sub-clustering within embedding clusters';


--
-- Name: COLUMN conversation_facet.conversation_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conversation_facet.conversation_id IS 'References conversations.id';


--
-- Name: COLUMN conversation_facet.pipeline_run_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conversation_facet.pipeline_run_id IS 'Run scoping per T-004 - links to pipeline_runs.id';


--
-- Name: COLUMN conversation_facet.action_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conversation_facet.action_type IS 'inquiry, complaint, bug_report, how_to_question, feature_request, account_change, delete_request';


--
-- Name: COLUMN conversation_facet.direction; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conversation_facet.direction IS 'excess, deficit, creation, deletion, modification, performance, neutral';


--
-- Name: COLUMN conversation_facet.symptom; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conversation_facet.symptom IS 'Brief description of user issue (10 words max)';


--
-- Name: COLUMN conversation_facet.user_goal; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conversation_facet.user_goal IS 'What user is trying to accomplish (10 words max)';


--
-- Name: conversation_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.conversation_summary AS
 SELECT conversations.issue_type,
    count(*) AS count,
    sum(
        CASE
            WHEN conversations.churn_risk THEN 1
            ELSE 0
        END) AS churn_risk_count,
    count(*) FILTER (WHERE (conversations.sentiment = 'frustrated'::text)) AS frustrated_count
   FROM public.conversations
  WHERE (conversations.created_at > (now() - '30 days'::interval))
  GROUP BY conversations.issue_type
  ORDER BY (count(*)) DESC;


--
-- Name: help_article_references; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.help_article_references (
    id integer NOT NULL,
    conversation_id text NOT NULL,
    article_id text NOT NULL,
    article_url text NOT NULL,
    article_title text,
    article_category text,
    referenced_at timestamp with time zone DEFAULT now()
);


--
-- Name: TABLE help_article_references; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.help_article_references IS 'Tracks help articles referenced by users in conversations (Phase 4a)';


--
-- Name: COLUMN help_article_references.article_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.help_article_references.article_id IS 'Intercom article ID extracted from URL';


--
-- Name: COLUMN help_article_references.article_url; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.help_article_references.article_url IS 'Canonical help article URL';


--
-- Name: COLUMN help_article_references.article_title; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.help_article_references.article_title IS 'Article title fetched from Intercom API';


--
-- Name: COLUMN help_article_references.article_category; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.help_article_references.article_category IS 'Article category/collection';


--
-- Name: conversations_with_articles; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.conversations_with_articles AS
 SELECT c.id,
    c.created_at,
    c.issue_type,
    c.sentiment,
    c.priority,
    array_agg(h.article_title) AS referenced_articles,
    count(h.id) AS article_count
   FROM (public.conversations c
     JOIN public.help_article_references h ON ((c.id = h.conversation_id)))
  GROUP BY c.id, c.created_at, c.issue_type, c.sentiment, c.priority
  ORDER BY c.created_at DESC;


--
-- Name: shortcut_story_links; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.shortcut_story_links (
    id integer NOT NULL,
    conversation_id text NOT NULL,
    story_id text NOT NULL,
    story_name text,
    story_labels jsonb DEFAULT '[]'::jsonb,
    story_epic text,
    story_state text,
    linked_at timestamp with time zone DEFAULT now()
);


--
-- Name: TABLE shortcut_story_links; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.shortcut_story_links IS 'Tracks Shortcut stories linked to conversations via Story ID v2 (Phase 4b)';


--
-- Name: COLUMN shortcut_story_links.story_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.shortcut_story_links.story_id IS 'Shortcut story ID from Story ID v2 custom attribute';


--
-- Name: COLUMN shortcut_story_links.story_labels; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.shortcut_story_links.story_labels IS 'JSON array of Shortcut story labels (product areas)';


--
-- Name: COLUMN shortcut_story_links.story_epic; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.shortcut_story_links.story_epic IS 'Epic name or ID if story belongs to an epic';


--
-- Name: conversations_with_stories; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.conversations_with_stories AS
 SELECT c.id,
    c.created_at,
    c.issue_type,
    c.sentiment,
    c.priority,
    s.story_id,
    s.story_name,
    s.story_labels,
    s.story_epic
   FROM (public.conversations c
     JOIN public.shortcut_story_links s ON ((c.id = s.conversation_id)))
  ORDER BY c.created_at DESC;


--
-- Name: theme_aggregates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.theme_aggregates (
    id integer NOT NULL,
    issue_signature text NOT NULL,
    product_area text NOT NULL,
    component text NOT NULL,
    occurrence_count integer DEFAULT 1,
    first_seen_at timestamp with time zone DEFAULT now(),
    last_seen_at timestamp with time zone DEFAULT now(),
    sample_user_intent text,
    sample_symptoms jsonb,
    sample_affected_flow text,
    sample_root_cause_hypothesis text,
    ticket_created boolean DEFAULT false,
    ticket_id text,
    ticket_excerpts jsonb DEFAULT '[]'::jsonb,
    source_counts jsonb DEFAULT '{}'::jsonb
);


--
-- Name: COLUMN theme_aggregates.source_counts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.theme_aggregates.source_counts IS 'Count of occurrences by source: {"intercom": N, "coda": M}';


--
-- Name: cross_source_themes; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.cross_source_themes AS
 SELECT ta.issue_signature,
    ta.product_area,
    ta.component,
    ta.occurrence_count AS total_conversations,
    ta.source_counts,
    COALESCE(((ta.source_counts ->> 'coda'::text))::integer, 0) AS coda_count,
    COALESCE(((ta.source_counts ->> 'intercom'::text))::integer, 0) AS intercom_count,
        CASE
            WHEN ((ta.source_counts ? 'coda'::text) AND (ta.source_counts ? 'intercom'::text)) THEN 'high_confidence'::text
            WHEN (ta.source_counts ? 'coda'::text) THEN 'strategic'::text
            ELSE 'tactical'::text
        END AS priority_category,
    ta.first_seen_at,
    ta.last_seen_at,
    ta.ticket_created,
    ta.ticket_id
   FROM public.theme_aggregates ta
  WHERE (ta.occurrence_count >= 1)
  ORDER BY (((COALESCE(((ta.source_counts ->> 'coda'::text))::integer, 0) > 0))::integer) DESC, COALESCE(((ta.source_counts ->> 'intercom'::text))::integer, 0) DESC;


--
-- Name: escalation_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.escalation_log (
    id integer NOT NULL,
    conversation_id text NOT NULL,
    rule_id text NOT NULL,
    action_type text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    slack_channel text,
    shortcut_story_id text,
    CONSTRAINT escalation_log_action_type_check CHECK ((action_type = ANY (ARRAY['slack_alert'::text, 'shortcut_ticket'::text, 'log_only'::text])))
);


--
-- Name: escalation_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.escalation_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: escalation_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.escalation_log_id_seq OWNED BY public.escalation_log.id;


--
-- Name: help_article_references_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.help_article_references_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: help_article_references_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.help_article_references_id_seq OWNED BY public.help_article_references.id;


--
-- Name: label_registry; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.label_registry (
    label_name character varying(100) NOT NULL,
    source character varying(20) NOT NULL,
    category character varying(50),
    created_at timestamp with time zone DEFAULT now(),
    last_seen_at timestamp with time zone DEFAULT now()
);


--
-- Name: TABLE label_registry; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.label_registry IS 'Label taxonomy from Shortcut plus internal extensions';


--
-- Name: most_linked_stories; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.most_linked_stories AS
 SELECT s.story_id,
    s.story_name,
    s.story_labels,
    s.story_epic,
    count(DISTINCT s.conversation_id) AS conversation_count,
    min(s.linked_at) AS first_linked,
    max(s.linked_at) AS last_linked,
    count(DISTINCT c.id) FILTER (WHERE (c.issue_type = 'bug_report'::text)) AS bug_count,
    count(DISTINCT c.id) FILTER (WHERE (c.issue_type = 'product_question'::text)) AS question_count,
    count(DISTINCT c.id) FILTER (WHERE (c.issue_type = 'feature_request'::text)) AS feature_request_count
   FROM (public.shortcut_story_links s
     LEFT JOIN public.conversations c ON ((s.conversation_id = c.id)))
  WHERE (s.linked_at > (now() - '30 days'::interval))
  GROUP BY s.story_id, s.story_name, s.story_labels, s.story_epic
  ORDER BY (count(DISTINCT s.conversation_id)) DESC;


--
-- Name: most_referenced_articles; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.most_referenced_articles AS
 SELECT h.article_id,
    h.article_title,
    h.article_category,
    count(DISTINCT h.conversation_id) AS reference_count,
    min(h.referenced_at) AS first_referenced,
    max(h.referenced_at) AS last_referenced,
    count(DISTINCT c.id) FILTER (WHERE (c.issue_type = ANY (ARRAY['bug_report'::text, 'product_question'::text]))) AS still_had_issues_count
   FROM (public.help_article_references h
     LEFT JOIN public.conversations c ON ((h.conversation_id = c.id)))
  WHERE (h.referenced_at > (now() - '30 days'::interval))
  GROUP BY h.article_id, h.article_title, h.article_category
  ORDER BY (count(DISTINCT h.conversation_id)) DESC;


--
-- Name: pipeline_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pipeline_runs (
    id integer NOT NULL,
    started_at timestamp with time zone DEFAULT now(),
    completed_at timestamp with time zone,
    date_from timestamp with time zone,
    date_to timestamp with time zone,
    conversations_fetched integer DEFAULT 0,
    conversations_filtered integer DEFAULT 0,
    conversations_classified integer DEFAULT 0,
    conversations_stored integer DEFAULT 0,
    status text,
    error_message text,
    current_phase character varying(50) DEFAULT 'classification'::character varying,
    auto_create_stories boolean DEFAULT false,
    themes_extracted integer DEFAULT 0,
    themes_new integer DEFAULT 0,
    stories_created integer DEFAULT 0,
    orphans_created integer DEFAULT 0,
    stories_ready boolean DEFAULT false,
    themes_filtered integer DEFAULT 0,
    errors jsonb DEFAULT '[]'::jsonb,
    warnings jsonb DEFAULT '[]'::jsonb,
    embeddings_generated integer DEFAULT 0,
    embeddings_failed integer DEFAULT 0,
    facets_extracted integer DEFAULT 0,
    facets_failed integer DEFAULT 0,
    checkpoint jsonb DEFAULT '{}'::jsonb,
    CONSTRAINT pipeline_runs_status_check CHECK ((status = ANY (ARRAY['running'::text, 'stopping'::text, 'stopped'::text, 'completed'::text, 'failed'::text])))
);


--
-- Name: COLUMN pipeline_runs.current_phase; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.current_phase IS 'Current execution phase: classification, embedding_generation, facet_extraction, theme_extraction, pm_review, story_creation, completed';


--
-- Name: COLUMN pipeline_runs.auto_create_stories; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.auto_create_stories IS 'Whether to automatically run PM review and create stories after theme extraction';


--
-- Name: COLUMN pipeline_runs.stories_ready; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.stories_ready IS 'True when theme extraction complete - stories can be created manually';


--
-- Name: COLUMN pipeline_runs.themes_filtered; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.themes_filtered IS 'Count of themes filtered by quality gates (low confidence, unknown vocabulary)';


--
-- Name: COLUMN pipeline_runs.errors; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.errors IS 'Array of structured errors: [{phase, message, details}, ...]';


--
-- Name: COLUMN pipeline_runs.warnings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.warnings IS 'Array of warning messages for non-fatal issues';


--
-- Name: COLUMN pipeline_runs.embeddings_generated; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.embeddings_generated IS 'Number of conversation embeddings successfully generated (#106)';


--
-- Name: COLUMN pipeline_runs.embeddings_failed; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.embeddings_failed IS 'Number of conversations where embedding generation failed (#106)';


--
-- Name: COLUMN pipeline_runs.facets_extracted; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.facets_extracted IS 'Number of conversations with successfully extracted facets';


--
-- Name: COLUMN pipeline_runs.facets_failed; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.facets_failed IS 'Number of conversations where facet extraction failed';


--
-- Name: COLUMN pipeline_runs.checkpoint; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pipeline_runs.checkpoint IS 'Checkpoint for resume: {phase, intercom_cursor, counts, updated_at}';


--
-- Name: pipeline_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pipeline_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pipeline_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pipeline_runs_id_seq OWNED BY public.pipeline_runs.id;


--
-- Name: research_embeddings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.research_embeddings (
    id integer NOT NULL,
    source_type character varying(50) NOT NULL,
    source_id character varying(255) NOT NULL,
    title text NOT NULL,
    content text NOT NULL,
    url text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb,
    content_hash character varying(64) NOT NULL,
    embedding public.vector(1536) NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: research_embeddings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.research_embeddings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: research_embeddings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.research_embeddings_id_seq OWNED BY public.research_embeddings.id;


--
-- Name: shortcut_story_links_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.shortcut_story_links_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: shortcut_story_links_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.shortcut_story_links_id_seq OWNED BY public.shortcut_story_links.id;


--
-- Name: stories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stories (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    title text NOT NULL,
    description text,
    labels text[] DEFAULT '{}'::text[],
    priority character varying(20),
    severity character varying(20),
    product_area character varying(100),
    technical_area character varying(100),
    status character varying(50) DEFAULT 'candidate'::character varying,
    confidence_score numeric(5,2),
    evidence_count integer DEFAULT 0,
    conversation_count integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    code_context jsonb,
    pipeline_run_id integer,
    grouping_method character varying(50) DEFAULT 'signature'::character varying,
    cluster_id character varying(255),
    cluster_metadata jsonb,
    implementation_context jsonb,
    actionability_score numeric(5,2),
    fix_size_score numeric(5,2),
    severity_score numeric(5,2),
    churn_risk_score numeric(5,2),
    score_metadata jsonb,
    excerpt_count integer DEFAULT 0
);


--
-- Name: TABLE stories; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.stories IS 'Canonical story records - system of record for FeedForward';


--
-- Name: COLUMN stories.grouping_method; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.stories.grouping_method IS 'How conversations were grouped: signature (legacy) or hybrid_cluster (#108/#109)';


--
-- Name: COLUMN stories.cluster_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.stories.cluster_id IS 'Hybrid cluster ID: emb_{n}_facet_{action_type}_{direction}';


--
-- Name: COLUMN stories.cluster_metadata; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.stories.cluster_metadata IS 'Facet metadata: {action_type, direction, embedding_cluster, conversation_count}';


--
-- Name: COLUMN stories.implementation_context; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.stories.implementation_context IS 'JSONB blob containing hybrid implementation context (schema v1.0): summary, relevant_files, next_steps, prior_art_references, metadata. See ImplementationContext model. Issue #180.';


--
-- Name: COLUMN stories.actionability_score; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.stories.actionability_score IS 'How actionable (0-100): impl context, resolution data, evidence quality';


--
-- Name: COLUMN stories.fix_size_score; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.stories.fix_size_score IS 'Estimated fix complexity (0-100): files involved, symptoms count';


--
-- Name: COLUMN stories.severity_score; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.stories.severity_score IS 'Business severity (0-100): priority mapping, error indicators';


--
-- Name: COLUMN stories.churn_risk_score; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.stories.churn_risk_score IS 'Customer churn risk (0-100): churn flag, org diversity';


--
-- Name: COLUMN stories.score_metadata; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.stories.score_metadata IS 'JSONB breakdown of per-factor scoring components for explainability';


--
-- Name: COLUMN stories.excerpt_count; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.stories.excerpt_count IS 'Number of evidence excerpts (diagnostic summaries + key excerpts). Issue #197.';


--
-- Name: story_evidence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.story_evidence (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    story_id uuid NOT NULL,
    conversation_ids text[] DEFAULT '{}'::text[],
    theme_signatures text[] DEFAULT '{}'::text[],
    source_stats jsonb DEFAULT '{}'::jsonb,
    excerpts jsonb DEFAULT '[]'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: TABLE story_evidence; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.story_evidence IS 'Evidence bundles linking stories to conversations and themes';


--
-- Name: story_sync_metadata; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.story_sync_metadata (
    story_id uuid NOT NULL,
    shortcut_story_id character varying(50),
    last_internal_update_at timestamp with time zone,
    last_external_update_at timestamp with time zone,
    last_synced_at timestamp with time zone,
    last_sync_status character varying(20),
    last_sync_error text,
    last_sync_direction character varying(10),
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: TABLE story_sync_metadata; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.story_sync_metadata IS 'Bidirectional sync state with Shortcut';


--
-- Name: stories_with_evidence; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.stories_with_evidence AS
 SELECT s.id,
    s.title,
    s.description,
    s.labels,
    s.priority,
    s.severity,
    s.product_area,
    s.technical_area,
    s.status,
    s.confidence_score,
    s.evidence_count,
    s.conversation_count,
    s.created_at,
    s.updated_at,
    se.conversation_ids,
    se.theme_signatures,
    se.source_stats,
    se.excerpts,
    sm.shortcut_story_id,
    sm.last_synced_at,
    sm.last_sync_status
   FROM ((public.stories s
     LEFT JOIN public.story_evidence se ON ((s.id = se.story_id)))
     LEFT JOIN public.story_sync_metadata sm ON ((s.id = sm.story_id)));


--
-- Name: story_comments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.story_comments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    story_id uuid NOT NULL,
    external_id character varying(100),
    source character varying(20) NOT NULL,
    body text NOT NULL,
    author character varying(255),
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: story_label_frequency; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.story_label_frequency AS
 SELECT label.value AS label,
    count(DISTINCT s.story_id) AS story_count,
    count(DISTINCT s.conversation_id) AS conversation_count,
    min(s.linked_at) AS first_seen,
    max(s.linked_at) AS last_seen
   FROM public.shortcut_story_links s,
    LATERAL jsonb_array_elements_text(s.story_labels) label(value)
  WHERE (s.linked_at > (now() - '30 days'::interval))
  GROUP BY label.value
  ORDER BY (count(DISTINCT s.story_id)) DESC;


--
-- Name: story_orphans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.story_orphans (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    signature text NOT NULL,
    original_signature text,
    conversation_ids text[] DEFAULT '{}'::text[] NOT NULL,
    theme_data jsonb DEFAULT '{}'::jsonb NOT NULL,
    confidence_score double precision,
    first_seen_at timestamp with time zone DEFAULT now(),
    last_updated_at timestamp with time zone DEFAULT now(),
    graduated_at timestamp with time zone,
    story_id uuid
);


--
-- Name: TABLE story_orphans; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.story_orphans IS 'Accumulates conversation groups with <3 items until they reach MIN_GROUP_SIZE for graduation to stories';


--
-- Name: COLUMN story_orphans.signature; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.story_orphans.signature IS 'PM-approved canonical signature from PM review splits';


--
-- Name: COLUMN story_orphans.original_signature; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.story_orphans.original_signature IS 'Original signature before PM review split (for lineage tracking)';


--
-- Name: COLUMN story_orphans.theme_data; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.story_orphans.theme_data IS 'Merged theme data: {user_intent, symptoms, excerpts[], product_area, component}';


--
-- Name: COLUMN story_orphans.graduated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.story_orphans.graduated_at IS 'Timestamp when orphan was converted to a story (NULL = still active)';


--
-- Name: suggested_evidence_decisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.suggested_evidence_decisions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    story_id uuid NOT NULL,
    evidence_id text NOT NULL,
    source_type text NOT NULL,
    source_id text NOT NULL,
    decision text NOT NULL,
    similarity_score numeric(5,4),
    decided_at timestamp with time zone DEFAULT now(),
    CONSTRAINT suggested_evidence_decisions_decision_check CHECK ((decision = ANY (ARRAY['accepted'::text, 'rejected'::text]))),
    CONSTRAINT suggested_evidence_decisions_evidence_id_check CHECK ((evidence_id <> ''::text)),
    CONSTRAINT suggested_evidence_decisions_similarity_score_check CHECK (((similarity_score >= (0)::numeric) AND (similarity_score <= (1)::numeric))),
    CONSTRAINT suggested_evidence_decisions_source_id_check CHECK ((source_id <> ''::text)),
    CONSTRAINT suggested_evidence_decisions_source_type_check CHECK ((source_type = ANY (ARRAY['coda_page'::text, 'coda_theme'::text, 'intercom'::text])))
);


--
-- Name: TABLE suggested_evidence_decisions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.suggested_evidence_decisions IS 'Tracks user accept/reject decisions for vector-suggested evidence on stories';


--
-- Name: COLUMN suggested_evidence_decisions.evidence_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.suggested_evidence_decisions.evidence_id IS 'Composite identifier in format "{source_type}:{source_id}" for unique evidence lookup';


--
-- Name: COLUMN suggested_evidence_decisions.source_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.suggested_evidence_decisions.source_type IS 'Evidence source type: coda_page (Coda documents), coda_theme (extracted themes), intercom (conversations)';


--
-- Name: COLUMN suggested_evidence_decisions.source_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.suggested_evidence_decisions.source_id IS 'Source-specific identifier (e.g., Coda page ID, conversation ID)';


--
-- Name: COLUMN suggested_evidence_decisions.similarity_score; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.suggested_evidence_decisions.similarity_score IS 'Vector similarity score (0-1) at decision time for audit/analytics';


--
-- Name: COLUMN suggested_evidence_decisions.decided_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.suggested_evidence_decisions.decided_at IS 'Timestamp when user made the accept/reject decision';


--
-- Name: theme_aggregates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.theme_aggregates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: theme_aggregates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.theme_aggregates_id_seq OWNED BY public.theme_aggregates.id;


--
-- Name: themes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.themes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: themes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.themes_id_seq OWNED BY public.themes.id;


--
-- Name: trending_themes; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.trending_themes AS
 SELECT t.issue_signature,
    t.product_area,
    t.component,
    count(*) AS occurrence_count,
    min(t.extracted_at) AS first_seen,
    max(t.extracted_at) AS last_seen,
    array_agg(DISTINCT c.contact_email) FILTER (WHERE (c.contact_email IS NOT NULL)) AS affected_users
   FROM (public.themes t
     JOIN public.conversations c ON ((t.conversation_id = c.id)))
  WHERE (t.extracted_at > (now() - '7 days'::interval))
  GROUP BY t.issue_signature, t.product_area, t.component
 HAVING (count(*) >= 2)
  ORDER BY (count(*)) DESC;


--
-- Name: context_usage_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.context_usage_logs ALTER COLUMN id SET DEFAULT nextval('public.context_usage_logs_id_seq'::regclass);


--
-- Name: escalation_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.escalation_log ALTER COLUMN id SET DEFAULT nextval('public.escalation_log_id_seq'::regclass);


--
-- Name: help_article_references id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.help_article_references ALTER COLUMN id SET DEFAULT nextval('public.help_article_references_id_seq'::regclass);


--
-- Name: pipeline_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_runs ALTER COLUMN id SET DEFAULT nextval('public.pipeline_runs_id_seq'::regclass);


--
-- Name: research_embeddings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_embeddings ALTER COLUMN id SET DEFAULT nextval('public.research_embeddings_id_seq'::regclass);


--
-- Name: shortcut_story_links id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shortcut_story_links ALTER COLUMN id SET DEFAULT nextval('public.shortcut_story_links_id_seq'::regclass);


--
-- Name: theme_aggregates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.theme_aggregates ALTER COLUMN id SET DEFAULT nextval('public.theme_aggregates_id_seq'::regclass);


--
-- Name: themes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.themes ALTER COLUMN id SET DEFAULT nextval('public.themes_id_seq'::regclass);


--
-- Name: context_usage_logs context_usage_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.context_usage_logs
    ADD CONSTRAINT context_usage_logs_pkey PRIMARY KEY (id);


--
-- Name: context_usage_logs context_usage_logs_theme_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.context_usage_logs
    ADD CONSTRAINT context_usage_logs_theme_id_unique UNIQUE (theme_id);


--
-- Name: conversation_embeddings conversation_embeddings_conversation_id_pipeline_run_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_embeddings
    ADD CONSTRAINT conversation_embeddings_conversation_id_pipeline_run_id_key UNIQUE (conversation_id, pipeline_run_id);


--
-- Name: conversation_embeddings conversation_embeddings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_embeddings
    ADD CONSTRAINT conversation_embeddings_pkey PRIMARY KEY (id);


--
-- Name: conversation_facet conversation_facet_conversation_id_pipeline_run_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_facet
    ADD CONSTRAINT conversation_facet_conversation_id_pipeline_run_id_key UNIQUE (conversation_id, pipeline_run_id);


--
-- Name: conversation_facet conversation_facet_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_facet
    ADD CONSTRAINT conversation_facet_pkey PRIMARY KEY (id);


--
-- Name: conversations conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (id);


--
-- Name: escalation_log escalation_log_conversation_id_rule_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.escalation_log
    ADD CONSTRAINT escalation_log_conversation_id_rule_id_key UNIQUE (conversation_id, rule_id);


--
-- Name: escalation_log escalation_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.escalation_log
    ADD CONSTRAINT escalation_log_pkey PRIMARY KEY (id);


--
-- Name: help_article_references help_article_references_conversation_id_article_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.help_article_references
    ADD CONSTRAINT help_article_references_conversation_id_article_id_key UNIQUE (conversation_id, article_id);


--
-- Name: help_article_references help_article_references_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.help_article_references
    ADD CONSTRAINT help_article_references_pkey PRIMARY KEY (id);


--
-- Name: label_registry label_registry_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.label_registry
    ADD CONSTRAINT label_registry_pkey PRIMARY KEY (label_name);


--
-- Name: pipeline_runs pipeline_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_runs
    ADD CONSTRAINT pipeline_runs_pkey PRIMARY KEY (id);


--
-- Name: research_embeddings research_embeddings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_embeddings
    ADD CONSTRAINT research_embeddings_pkey PRIMARY KEY (id);


--
-- Name: research_embeddings research_embeddings_source_type_source_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_embeddings
    ADD CONSTRAINT research_embeddings_source_type_source_id_key UNIQUE (source_type, source_id);


--
-- Name: shortcut_story_links shortcut_story_links_conversation_id_story_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shortcut_story_links
    ADD CONSTRAINT shortcut_story_links_conversation_id_story_id_key UNIQUE (conversation_id, story_id);


--
-- Name: shortcut_story_links shortcut_story_links_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shortcut_story_links
    ADD CONSTRAINT shortcut_story_links_pkey PRIMARY KEY (id);


--
-- Name: stories stories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stories
    ADD CONSTRAINT stories_pkey PRIMARY KEY (id);


--
-- Name: story_comments story_comments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.story_comments
    ADD CONSTRAINT story_comments_pkey PRIMARY KEY (id);


--
-- Name: story_comments story_comments_story_id_external_id_source_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.story_comments
    ADD CONSTRAINT story_comments_story_id_external_id_source_key UNIQUE (story_id, external_id, source);


--
-- Name: story_evidence story_evidence_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.story_evidence
    ADD CONSTRAINT story_evidence_pkey PRIMARY KEY (id);


--
-- Name: story_orphans story_orphans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.story_orphans
    ADD CONSTRAINT story_orphans_pkey PRIMARY KEY (id);


--
-- Name: story_orphans story_orphans_signature_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.story_orphans
    ADD CONSTRAINT story_orphans_signature_key UNIQUE (signature);


--
-- Name: story_sync_metadata story_sync_metadata_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.story_sync_metadata
    ADD CONSTRAINT story_sync_metadata_pkey PRIMARY KEY (story_id);


--
-- Name: suggested_evidence_decisions suggested_evidence_decisions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suggested_evidence_decisions
    ADD CONSTRAINT suggested_evidence_decisions_pkey PRIMARY KEY (id);


--
-- Name: suggested_evidence_decisions suggested_evidence_decisions_story_id_evidence_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suggested_evidence_decisions
    ADD CONSTRAINT suggested_evidence_decisions_story_id_evidence_id_key UNIQUE (story_id, evidence_id);


--
-- Name: theme_aggregates theme_aggregates_issue_signature_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.theme_aggregates
    ADD CONSTRAINT theme_aggregates_issue_signature_key UNIQUE (issue_signature);


--
-- Name: theme_aggregates theme_aggregates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.theme_aggregates
    ADD CONSTRAINT theme_aggregates_pkey PRIMARY KEY (id);


--
-- Name: themes themes_conversation_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.themes
    ADD CONSTRAINT themes_conversation_id_key UNIQUE (conversation_id);


--
-- Name: themes themes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.themes
    ADD CONSTRAINT themes_pkey PRIMARY KEY (id);


--
-- Name: idx_context_usage_logs_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_context_usage_logs_created_at ON public.context_usage_logs USING btree (created_at);


--
-- Name: idx_context_usage_logs_pipeline_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_context_usage_logs_pipeline_run ON public.context_usage_logs USING btree (pipeline_run_id);


--
-- Name: idx_context_usage_logs_theme_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_context_usage_logs_theme_id ON public.context_usage_logs USING btree (theme_id);


--
-- Name: idx_conv_embeddings_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conv_embeddings_hnsw ON public.conversation_embeddings USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: idx_conv_embeddings_run_conv; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conv_embeddings_run_conv ON public.conversation_embeddings USING btree (pipeline_run_id, conversation_id);


--
-- Name: idx_conv_facet_action_direction; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conv_facet_action_direction ON public.conversation_facet USING btree (pipeline_run_id, action_type, direction);


--
-- Name: idx_conv_facet_run_conv; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conv_facet_run_conv ON public.conversation_facet USING btree (pipeline_run_id, conversation_id);


--
-- Name: idx_conversations_churn_risk; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_churn_risk ON public.conversations USING btree (churn_risk) WHERE (churn_risk = true);


--
-- Name: idx_conversations_classification_changed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_classification_changed ON public.conversations USING btree (classification_changed) WHERE (classification_changed = true);


--
-- Name: idx_conversations_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_created_at ON public.conversations USING btree (created_at DESC);


--
-- Name: idx_conversations_data_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_data_source ON public.conversations USING btree (data_source);


--
-- Name: idx_conversations_disambiguation_level; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_disambiguation_level ON public.conversations USING btree (disambiguation_level) WHERE ((disambiguation_level)::text = ANY ((ARRAY['high'::character varying, 'medium'::character varying])::text[]));


--
-- Name: idx_conversations_has_support_response; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_has_support_response ON public.conversations USING btree (has_support_response) WHERE (has_support_response = true);


--
-- Name: idx_conversations_issue_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_issue_type ON public.conversations USING btree (issue_type);


--
-- Name: idx_conversations_pipeline_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_pipeline_run_id ON public.conversations USING btree (pipeline_run_id);


--
-- Name: idx_conversations_priority; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_priority ON public.conversations USING btree (priority) WHERE (priority = ANY (ARRAY['urgent'::text, 'high'::text]));


--
-- Name: idx_conversations_stage1_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_stage1_type ON public.conversations USING btree (stage1_type) WHERE (stage1_type IS NOT NULL);


--
-- Name: idx_conversations_stage2_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_stage2_type ON public.conversations USING btree (stage2_type) WHERE (stage2_type IS NOT NULL);


--
-- Name: idx_conversations_story_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_story_id ON public.conversations USING btree (story_id) WHERE (story_id IS NOT NULL);


--
-- Name: idx_escalation_log_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_escalation_log_conversation ON public.escalation_log USING btree (conversation_id);


--
-- Name: idx_escalation_log_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_escalation_log_created_at ON public.escalation_log USING btree (created_at DESC);


--
-- Name: idx_evidence_decisions_story_decision; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_evidence_decisions_story_decision ON public.suggested_evidence_decisions USING btree (story_id, decision);


--
-- Name: idx_help_article_references_article_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_help_article_references_article_id ON public.help_article_references USING btree (article_id);


--
-- Name: idx_help_article_references_conversation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_help_article_references_conversation_id ON public.help_article_references USING btree (conversation_id);


--
-- Name: idx_help_article_references_referenced_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_help_article_references_referenced_at ON public.help_article_references USING btree (referenced_at DESC);


--
-- Name: idx_orphans_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_orphans_active ON public.story_orphans USING btree (signature) WHERE (graduated_at IS NULL);


--
-- Name: idx_orphans_first_seen; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_orphans_first_seen ON public.story_orphans USING btree (first_seen_at DESC);


--
-- Name: idx_orphans_signature; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_orphans_signature ON public.story_orphans USING btree (signature);


--
-- Name: idx_orphans_story; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_orphans_story ON public.story_orphans USING btree (story_id) WHERE (story_id IS NOT NULL);


--
-- Name: idx_stories_actionability; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stories_actionability ON public.stories USING btree (actionability_score);


--
-- Name: idx_stories_churn_risk; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stories_churn_risk ON public.stories USING btree (churn_risk_score);


--
-- Name: idx_stories_confidence; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stories_confidence ON public.stories USING btree (confidence_score DESC);


--
-- Name: idx_stories_excerpt_count; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stories_excerpt_count ON public.stories USING btree (excerpt_count);


--
-- Name: idx_stories_fix_size; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stories_fix_size ON public.stories USING btree (fix_size_score);


--
-- Name: idx_stories_grouping_method; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stories_grouping_method ON public.stories USING btree (grouping_method);


--
-- Name: idx_stories_has_impl_context; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stories_has_impl_context ON public.stories USING btree (((implementation_context IS NOT NULL))) WHERE (implementation_context IS NOT NULL);


--
-- Name: idx_stories_impl_context_success; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stories_impl_context_success ON public.stories USING btree (((implementation_context ->> 'success'::text))) WHERE (implementation_context IS NOT NULL);


--
-- Name: idx_stories_pipeline_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stories_pipeline_run_id ON public.stories USING btree (pipeline_run_id);


--
-- Name: idx_stories_product_area; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stories_product_area ON public.stories USING btree (product_area);


--
-- Name: idx_stories_severity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stories_severity ON public.stories USING btree (severity_score);


--
-- Name: idx_stories_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stories_status ON public.stories USING btree (status);


--
-- Name: idx_stories_updated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stories_updated_at ON public.stories USING btree (updated_at DESC);


--
-- Name: idx_story_comments_story_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_story_comments_story_id ON public.story_comments USING btree (story_id);


--
-- Name: idx_story_evidence_story_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_story_evidence_story_id ON public.story_evidence USING btree (story_id);


--
-- Name: idx_story_links_conversation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_story_links_conversation_id ON public.shortcut_story_links USING btree (conversation_id);


--
-- Name: idx_story_links_linked_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_story_links_linked_at ON public.shortcut_story_links USING btree (linked_at DESC);


--
-- Name: idx_story_links_story_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_story_links_story_id ON public.shortcut_story_links USING btree (story_id);


--
-- Name: idx_sync_metadata_last_synced; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sync_metadata_last_synced ON public.story_sync_metadata USING btree (last_synced_at);


--
-- Name: idx_sync_metadata_shortcut_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sync_metadata_shortcut_id ON public.story_sync_metadata USING btree (shortcut_story_id);


--
-- Name: idx_theme_aggregates_count; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_theme_aggregates_count ON public.theme_aggregates USING btree (occurrence_count DESC);


--
-- Name: idx_theme_aggregates_last_seen; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_theme_aggregates_last_seen ON public.theme_aggregates USING btree (last_seen_at DESC);


--
-- Name: idx_theme_aggregates_source_counts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_theme_aggregates_source_counts ON public.theme_aggregates USING gin (source_counts);


--
-- Name: idx_themes_component_drift; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_themes_component_drift ON public.themes USING btree (component, component_raw);


--
-- Name: idx_themes_data_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_themes_data_source ON public.themes USING btree (data_source);


--
-- Name: idx_themes_extracted_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_themes_extracted_at ON public.themes USING btree (extracted_at DESC);


--
-- Name: idx_themes_issue_signature; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_themes_issue_signature ON public.themes USING btree (issue_signature);


--
-- Name: idx_themes_pipeline_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_themes_pipeline_run_id ON public.themes USING btree (pipeline_run_id);


--
-- Name: idx_themes_product_area; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_themes_product_area ON public.themes USING btree (product_area);


--
-- Name: idx_themes_quality_score; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_themes_quality_score ON public.themes USING btree (quality_score) WHERE (quality_score IS NOT NULL);


--
-- Name: idx_themes_resolution_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_themes_resolution_category ON public.themes USING btree (resolution_category) WHERE (resolution_category IS NOT NULL);


--
-- Name: research_embeddings_embedding_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX research_embeddings_embedding_idx ON public.research_embeddings USING ivfflat (embedding public.vector_cosine_ops) WITH (lists='100');


--
-- Name: stories stories_updated_at_trigger; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER stories_updated_at_trigger BEFORE UPDATE ON public.stories FOR EACH ROW EXECUTE FUNCTION public.update_stories_updated_at();


--
-- Name: context_usage_logs context_usage_logs_pipeline_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.context_usage_logs
    ADD CONSTRAINT context_usage_logs_pipeline_run_id_fkey FOREIGN KEY (pipeline_run_id) REFERENCES public.pipeline_runs(id) ON DELETE SET NULL;


--
-- Name: context_usage_logs context_usage_logs_theme_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.context_usage_logs
    ADD CONSTRAINT context_usage_logs_theme_id_fkey FOREIGN KEY (theme_id) REFERENCES public.themes(id) ON DELETE CASCADE;


--
-- Name: conversation_embeddings conversation_embeddings_pipeline_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_embeddings
    ADD CONSTRAINT conversation_embeddings_pipeline_run_id_fkey FOREIGN KEY (pipeline_run_id) REFERENCES public.pipeline_runs(id) ON DELETE SET NULL;


--
-- Name: conversation_facet conversation_facet_pipeline_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_facet
    ADD CONSTRAINT conversation_facet_pipeline_run_id_fkey FOREIGN KEY (pipeline_run_id) REFERENCES public.pipeline_runs(id) ON DELETE SET NULL;


--
-- Name: conversations conversations_pipeline_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_pipeline_run_id_fkey FOREIGN KEY (pipeline_run_id) REFERENCES public.pipeline_runs(id) ON DELETE SET NULL;


--
-- Name: escalation_log escalation_log_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.escalation_log
    ADD CONSTRAINT escalation_log_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id);


--
-- Name: help_article_references help_article_references_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.help_article_references
    ADD CONSTRAINT help_article_references_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: shortcut_story_links shortcut_story_links_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shortcut_story_links
    ADD CONSTRAINT shortcut_story_links_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: stories stories_pipeline_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stories
    ADD CONSTRAINT stories_pipeline_run_id_fkey FOREIGN KEY (pipeline_run_id) REFERENCES public.pipeline_runs(id);


--
-- Name: story_comments story_comments_story_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.story_comments
    ADD CONSTRAINT story_comments_story_id_fkey FOREIGN KEY (story_id) REFERENCES public.stories(id) ON DELETE CASCADE;


--
-- Name: story_evidence story_evidence_story_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.story_evidence
    ADD CONSTRAINT story_evidence_story_id_fkey FOREIGN KEY (story_id) REFERENCES public.stories(id) ON DELETE CASCADE;


--
-- Name: story_orphans story_orphans_story_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.story_orphans
    ADD CONSTRAINT story_orphans_story_id_fkey FOREIGN KEY (story_id) REFERENCES public.stories(id);


--
-- Name: story_sync_metadata story_sync_metadata_story_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.story_sync_metadata
    ADD CONSTRAINT story_sync_metadata_story_id_fkey FOREIGN KEY (story_id) REFERENCES public.stories(id) ON DELETE CASCADE;


--
-- Name: suggested_evidence_decisions suggested_evidence_decisions_story_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suggested_evidence_decisions
    ADD CONSTRAINT suggested_evidence_decisions_story_id_fkey FOREIGN KEY (story_id) REFERENCES public.stories(id) ON DELETE CASCADE;


--
-- Name: themes themes_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.themes
    ADD CONSTRAINT themes_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id);


--
-- Name: themes themes_pipeline_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.themes
    ADD CONSTRAINT themes_pipeline_run_id_fkey FOREIGN KEY (pipeline_run_id) REFERENCES public.pipeline_runs(id);


--
-- PostgreSQL database dump complete
--
