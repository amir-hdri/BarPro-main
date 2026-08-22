export interface ApiResponse<T> {
  data?: T;
  error?: string;
  success: boolean;
}

export interface ClientProfile {
  id: number;
  client_code: string;
  name: string;
  email: string;
  phone?: string | null;
  status: string;
  max_drivers: number;
  max_plates: number;
  max_concurrent_tasks: number;
  max_daily_tasks: number;
  created_at: string;
  last_login_at?: string | null;
}

export interface AuthLoginResponse {
  token_type: string;
  expires_in: number;
  client: ClientProfile;
}

export interface AdminProfile {
  username: string;
  role: 'master_admin';
}

export interface AdminLoginResponse {
  token_type: string;
  expires_in: number;
  admin: AdminProfile;
}

export interface ClientRegisterRequest {
  client_code: string;
  name: string;
  email: string;
  phone?: string;
  password: string;
  max_drivers?: number;
  max_plates?: number;
}

export interface AdminClientUpdateRequest {
  client_code?: string;
  name?: string;
  email?: string;
  phone?: string;
  password?: string;
  status?: string;
  max_drivers?: number;
  max_plates?: number;
  max_concurrent_tasks?: number;
  max_daily_tasks?: number;
}

export interface ClientStats {
  client_id: number;
  total_drivers: number;
  active_drivers: number;
  total_jobs: number;
  pending_jobs: number;
  in_progress_jobs: number;
  success_jobs: number;
  failed_jobs: number;
  today_jobs: number;
  today_success: number;
  today_failed: number;
  success_rate: number;
  created_at: string;
}

export interface Driver {
  id: number;
  client_id: number;
  driver_national_code: string;
  full_name: string;
  phone?: string | null;
  license_number?: string | null;
  utcms_username: string;
  status: string;
  runtime_status?: string | null;
  last_auth_at?: string | null;
  last_session_expires_at?: string | null;
  last_error_code?: string | null;
  active_plate?: string | null;
  created_at: string;
  updated_at: string;
}

export interface DriverCreateRequest {
  driver_national_code: string;
  full_name: string;
  phone?: string;
  license_number?: string;
  utcms_username: string;
  utcms_password: string;
  plate_number?: string;
  vehicle_type?: string;
}

export interface FuelInquiryCreateRequest {
  driver_id: number;
  year?: number;
  month?: number;
  force_retry?: boolean;
  plate_number?: string;
}

export interface DriverUpdateRequest {
  driver_national_code?: string;
  full_name?: string;
  phone?: string;
  license_number?: string;
  utcms_username?: string;
  utcms_password?: string;
  plate_number?: string;
  vehicle_type?: string;
  status?: string;
}

export interface Plate {
  id: number;
  client_id: number;
  driver_id: number;
  plate_number: string;
  vehicle_type?: string | null;
  status: string;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlateCreateRequest {
  driver_id: number;
  plate_number: string;
  vehicle_type?: string;
  status?: string;
  notes?: string;
}

export interface PlateUpdateRequest {
  plate_number?: string;
  vehicle_type?: string;
  status?: string;
  notes?: string;
}

export interface DriverSchedule {
  id: number;
  client_id: number;
  driver_id: number;
  title: string;
  frequency: 'daily' | 'weekly' | string;
  run_time: string;
  run_times: string[];
  weekdays: number[];
  specific_dates: string[];
  start_date?: string | null;
  end_date?: string | null;
  timezone: string;
  payload_template: Record<string, unknown>;
  is_active: boolean;
  last_run_at?: string | null;
  next_run_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface DriverScheduleCreateRequest {
  driver_id: number;
  title: string;
  frequency: 'daily' | 'weekly' | 'once';
  run_time: string;
  run_times?: string[];
  weekdays?: number[];
  specific_dates?: string[];
  start_date?: string;
  end_date?: string;
  timezone?: string;
  payload_template: Record<string, unknown>;
  is_active?: boolean;
}

export interface WaybillPayload {
  driver_national_code: string;
  driver_phone?: string;
  origin: string;
  origin_province: string;
  origin_address: string;
  origin_district?: string;
  destination: string;
  destination_province: string;
  destination_address: string;
  destination_district?: string;
  plate_number: string;
  vehicle_type?: string;
  cargo_type?: string;
  cargo_packaging?: string;
  cargo_weight?: string;
  cargo_value?: string;
  sender_name: string;
  receiver_name: string;
}

export interface WaybillJobCreateRequest {
  driver_national_code: string;
  payload: Record<string, unknown>;
  max_retries?: number;
  priority?: number;
  idempotency_key?: string;
}

export interface WaybillJobUpdateRequest {
  priority?: number;
  max_retries?: number;
  terminal_reason?: string;
  business_date?: string;
  correlation_id?: string;
}

export interface WaybillJob {
  driver_name?: string;
  id: number;
  job_id: string;
  client_id: number;
  driver_id?: number | null;
  status: string;
  source: string;
  correlation_id?: string | null;
  business_date?: string | null;
  priority: number;
  last_error?: string | null;
  error_category?: string | null;
  next_retry_at?: string | null;
  submit_after?: string | null;
  terminal_reason?: string | null;
  batch_id?: number | null;
  route_template_id?: number | null;
  sequence_index?: number | null;
  distance_km?: number | null;
  duration_min?: number | null;
  attempt_count: number;
  max_retries: number;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  payload_json?: Record<string, unknown> | string | null;
  result_json?: Record<string, unknown> | string | null;
  mutation_status?: string | null;
  reconciled_at?: string | null;
  night_attempt_count?: number;
  night_attempt_window?: string | null;
  client_name?: string | null;
  client_code?: string | null;
}

export interface WaybillTaskListResponse {
  tasks: WaybillJob[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface TimelineEntry {
  entry_id: string;
  job_id: string;
  source: string;
  event_type: string;
  phase?: string | null;
  title: string;
  status?: string | null;
  message?: string | null;
  payload?: Record<string, unknown> | null;
  created_at: string;
}

export interface JobTimelineResponse {
  job_id: string;
  entries: TimelineEntry[];
  total: number;
  page: number;
  page_size: number;
  progress_percent?: number;
}

export interface ReportMetricCard {
  label: string;
  value: string;
  hint: string;
}

export interface AdminClientSummary {
  rows: Array<{
    client_id: number;
    client_code: string;
    name: string;
    email: string;
    status: string;
    total_drivers: number;
    active_drivers: number;
    total_plates: number;
    active_plates: number;
    total_jobs: number;
    success_jobs: number;
    failed_jobs: number;
    success_rate: number;
    failure_reasons: Record<string, number>;
    first_activity?: string;
    last_activity?: string;
    created_at: string;
  }>;
  total_clients: number;
  active_clients: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface DriverReport {
  jobs: Array<{
    job_id: string;
    client_id: number;
    client_name: string;
    driver_id: number;
    driver_name: string;
    driver_national_code?: string;
    plate_number?: string;
    status: string;
    source: string;
    last_error?: string;
    error_category?: string;
    attempt_count?: number;
    created_at: string;
    finished_at?: string;
  }>;

  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ReportFilterOptions {
  clients: Array<{ id: number; name: string; client_code: string }>;
  drivers: Array<{ id: number; client_id: number; full_name: string; driver_national_code: string }>;
  plates: Array<{ id: number; client_id: number; driver_id: number; plate_number: string }>;
}

export interface FailureAnalysis {
  by_category: Record<string, number>;
  by_client: Record<string, number>;
  examples: Record<string, Array<{
    client: string;
    driver: string;
    error: string;
    created_at: string;
  }>>;
  total_failed: number;
}

export interface WebSocketEvent {
  type: string;
  job_id?: string;
  status?: string;
  message?: string;
  data?: Record<string, unknown>;
  timestamp?: string;
  [key: string]: unknown;
}

export interface CircuitBreakerDetail {
  state: string;
  failure_count: number;
  retry_after_seconds: number;
  enabled: boolean;
}

export interface ReadyzResponse {
  status: string;
  details?: {
    circuit_breaker?: {
      status: CircuitBreakerDetail;
    };
  };
}

export interface ClientEditData {
  id: string | number;
  client_code: string;
  name: string;
  email: string;
  phone?: string;
  max_drivers: number;
  max_plates: number;
  max_concurrent_tasks: number;
  max_daily_tasks: number;
  status: string;
  access_level?: string;
  subscription_start_date?: string;
  subscription_end_date?: string;
}

export interface UserFilterOptions {
  drivers: Array<{ id: number; full_name: string; driver_national_code: string }>;
  plates: Array<{ id: number; driver_id?: number; plate_number: string }>;
}

export interface UserWaybillItem {
  job_id: string;
  driver_id: number;
  driver_name?: string;
  driver_national_code?: string;
  plate_number?: string;
  status: string;
  source: string;
  business_date?: string;
  last_error?: string;
  error_category?: string;
  attempt_count?: number;
  created_at: string;
  started_at?: string;
  finished_at?: string;
  is_scheduled?: boolean;
  schedule_id?: number;
}

export interface UserWaybillHistoryResponse {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  jobs: UserWaybillItem[];
}

export interface FuelQuotaData {
  tables?: Array<{
    table_index: number;
    headers: string[];
    rows: string[][];
  }>;
  key_values?: Record<string, string>;
  summary?: {
    base_quota?: string;
    performance_quota?: string;
    card_number?: string;
  };
}

export interface FuelInquiryItem {
  id: number;
  client_id: number;
  driver_id: number;
  driver_name?: string | null;
  status: string;
  error_message?: string | null;
  quota_data?: FuelQuotaData | null;
  screenshot_url?: string | null;
  created_at: string;
  updated_at: string;
  year?: number | null;
  month?: number | null;
  plate_number?: string | null;
  client_name?: string | null;
  client_code?: string | null;
}

export type FuelInquiry = FuelInquiryItem;

export interface FuelInquiryListResponse {
  items: FuelInquiryItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ClientItem {
  id: number;
  client_code: string;
  name: string;
  email: string;
  phone: string;
  status: string;
  max_drivers: number;
  max_plates: number;
  max_concurrent_tasks: number;
  max_daily_tasks: number;
  access_level?: string;
  created_at: string;
  subscription_start_date?: string;
  subscription_end_date?: string;
}

export interface ClientDetail {
  total_jobs: number;
  success_jobs: number;
  failed_jobs: number;
  success_rate: number;
  total_drivers: number;
  active_drivers: number;
  total_plates: number;
  failure_reasons: Record<string, number>;
  driver_breakdown: Array<{
    driver_name: string;
    total_jobs: number;
    success: number;
    failed: number;
    success_rate: number;
  }>;
}

// ─── Multi-route + distance/time feature ────────────────────────────────────

export interface WaybillRouteTemplate {
  id: number;
  client_id: number;
  name: string;
  origin_province?: string | null;
  origin_city?: string | null;
  origin_address?: string | null;
  origin_lat?: number | null;
  origin_lng?: number | null;
  dest_province?: string | null;
  dest_city?: string | null;
  dest_address?: string | null;
  dest_lat?: number | null;
  dest_lng?: number | null;
  distance_km?: number | null;
  duration_min?: number | null;
  is_favorite: boolean;
  created_at: string;
  updated_at: string;
}

export interface RouteTemplateCreateRequest {
  name: string;
  origin_province?: string;
  origin_city?: string;
  origin_address?: string;
  origin_lat?: number;
  origin_lng?: number;
  dest_province?: string;
  dest_city?: string;
  dest_address?: string;
  dest_lat?: number;
  dest_lng?: number;
  is_favorite?: boolean;
}

export interface RouteTemplateUpdateRequest {
  name?: string;
  origin_province?: string | null;
  origin_city?: string | null;
  origin_address?: string | null;
  origin_lat?: number | null;
  origin_lng?: number | null;
  dest_province?: string | null;
  dest_city?: string | null;
  dest_address?: string | null;
  dest_lat?: number | null;
  dest_lng?: number | null;
  is_favorite?: boolean | null;
}

export interface DistanceRequest {
  origin_lat: number;
  origin_lng: number;
  dest_lat: number;
  dest_lng: number;
}

export interface DistanceResponse {
  distance_km: number;
  duration_min: number;
  distance_text: string;
  duration_text: string;
  source: string;
}

export interface BatchCreateRequest {
  driver_id: number;
  name?: string;
  route_template_ids: number[];
  base_payload_json: Record<string, unknown>;
  target_count?: number;
  repeat_mode?: 'round_robin' | 'random' | 'sequential';
  interval_minutes?: number;
  priority?: number;
}

export interface WaybillBatch {
  id: number;
  client_id: number;
  idempotency_key?: string | null;
  driver_id?: number | null;
  name?: string | null;
  route_template_ids: number[];
  base_payload_json?: Record<string, unknown> | null;
  target_count: number;
  repeat_mode: string;
  interval_minutes: number;
  status: string;
  progress: { completed: number; failed: number; today: number };
  created_at: string;
  updated_at: string;
}

export interface BatchProgressResponse {
  batch_id: number;
  target: number;
  completed: number;
  failed: number;
  today: number;
  progress_percent: number;
  status: string;
}
