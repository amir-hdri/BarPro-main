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
  access_token: string;
  token_type: string;
  expires_in: number;
  client: ClientProfile;
}

export interface AdminProfile {
  username: string;
  role: 'master_admin';
}

export interface AdminLoginResponse {
  access_token: string;
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
}

export interface DriverUpdateRequest {
  full_name?: string;
  phone?: string;
  license_number?: string;
  utcms_username?: string;
  utcms_password?: string;
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
  frequency: 'daily' | 'weekly';
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
  origin: string;
  origin_province: string;
  origin_address: string;
  origin_district?: string;
  destination: string;
  destination_province: string;
  destination_address: string;
  destination_district?: string;
  plate_number: string;
  waybill_number?: string;
  cargo_type?: string;
  cargo_weight?: string;
  cargo_count?: string;
  cargo_description?: string;
  cargo_value?: string;
  vehicle_type?: string;
  driver_phone?: string;
  sender_name: string;
  sender_phone: string;
  sender_national_code: string;
  sender_address: string;
  receiver_name: string;
  receiver_phone: string;
  receiver_national_code?: string;
  receiver_address: string;
  financial_cost?: string;
  financial_payment_method?: string;
  shipping_two_way?: boolean;
  shipping_time_limit?: string;
  shipping_end_shipping?: string;
  shipping_otp?: string;
  notes?: string;
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
  status?: string;
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
  attempt_count: number;
  max_retries: number;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
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
}
