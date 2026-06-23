/**
 * Shared type definitions for the application.
 */

// Auth
export interface ClientUser {
  id: number;
  client_code: string;
  name: string;
  email: string;
  phone?: string;
  status: string;
  max_drivers: number;
  max_plates: number;
  max_concurrent_tasks: number;
  max_daily_tasks: number;
  created_at: string;
  last_login_at?: string;
}

export interface AdminUser {
  id: number;
  username: string;
  email: string;
  full_name?: string;
  is_active: boolean;
  last_login_at?: string;
}

// Driver
export interface Driver {
  id: number;
  client_id: number;
  driver_national_code: string;
  full_name: string;
  phone?: string;
  license_number?: string;
  utcms_username: string;
  status: string;
  runtime_status?: string;
  last_auth_at?: string;
  last_session_expires_at?: string;
  last_error_code?: string;
  created_at: string;
  updated_at: string;
  plates?: { id: number; plate_number: string; vehicle_type?: string; status: string }[];
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

// Plate
export interface DriverPlate {
  id: number;
  driver_id: number;
  plate_number: string;
  vehicle_type?: string;
  status: string;
  notes?: string;
  created_at: string;
  updated_at: string;
}

// Waybill
export interface WaybillJob {
  id: number;
  job_id: string;
  client_id: number;
  driver_id?: number;
  status: string;
  source: string;
  correlation_id?: string;
  business_date?: string;
  priority: number;
  last_error?: string;
  error_category?: string;
  next_retry_at?: string;
  submit_after?: string;
  terminal_reason?: string;
  attempt_count: number;
  max_retries: number;
  created_at: string;
  updated_at: string;
  started_at?: string;
  finished_at?: string;
  schedule_id?: number;
  result_json?: Record<string, any> | null;
}

export interface WaybillJobCreateRequest {
  driver_national_code: string;
  payload: Record<string, any>;
  max_retries?: number;
  idempotency_key?: string;
  correlation_id?: string;
  priority?: number;
}

// Schedule
export interface DriverSchedule {
  id: number;
  client_id: number;
  driver_id: number;
  title: string;
  frequency: string;
  run_time: string;
  run_times: string[];
  weekdays: number[];
  specific_dates: string[];
  start_date?: string;
  end_date?: string;
  timezone: string;
  payload_template: Record<string, any>;
  is_active: boolean;
  last_run_at?: string;
  next_run_at?: string;
  created_at: string;
  updated_at: string;
}

export interface ScheduleCreateRequest {
  driver_id: number;
  title: string;
  frequency?: string;
  run_time?: string;
  run_times?: string[];
  weekdays?: number[];
  specific_dates?: string[];
  start_date?: string;
  end_date?: string;
  timezone?: string;
  payload_template?: Record<string, any>;
  is_active?: boolean;
}

// Stats
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

// Admin report
export interface AdminClientSummary {
  total_clients: number;
  active_clients: number;
  page: number;
  page_size: number;
  total_rows: number;
  rows: {
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
  }[];
}

export interface DriverReport {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  jobs: {
    job_id: string;
    client_id: number;
    client_name?: string;
    driver_id?: number;
    driver_name?: string;
    driver_national_code?: string;
    status: string;
    source: string;
    business_date?: string;
    last_error?: string;
    error_category?: string;
    attempt_count: number;
    created_at: string;
    started_at?: string;
    finished_at?: string;
  }[];
}

export interface FailureAnalysis {
  total_failed: number;
  by_category: Record<string, number>;
  by_client: Record<string, number>;
  by_driver: Record<string, number>;
  examples: Record<string, any[]>;
}

// User reports
export interface UserDriverStatus {
  driver_id: number;
  driver_name: string;
  national_code: string;
  phone?: string;
  status: string;
  runtime_status?: string;
  last_auth_at?: string;
  last_session_expires_at?: string;
  last_error_code?: string;
  total_jobs: number;
  success_jobs: number;
  failed_jobs: number;
  pending_jobs: number;
  success_rate: number;
  schedules: { id: number; title: string; is_active: boolean; frequency: string; next_run_at?: string; last_run_at?: string }[];
  plates: { id: number; plate_number: string; vehicle_type?: string; status: string }[];
}

export interface WaybillHistory {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  jobs: {
    job_id: string;
    driver_id?: number;
    driver_name?: string;
    driver_national_code?: string;
    status: string;
    source: string;
    business_date?: string;
    last_error?: string;
    error_category?: string;
    attempt_count: number;
    created_at: string;
    started_at?: string;
    finished_at?: string;
    is_scheduled: boolean;
    schedule_id?: number;
  }[];
}

export interface ErrorDetail {
  job_id: string;
  driver_id?: number;
  driver_name?: string;
  status: string;
  error_category?: string;
  last_error?: string;
  attempt_count: number;
  created_at: string;
  steps: { step: string; status: string; message?: string; created_at: string }[];
}

export interface ScheduledExecutionHistory {
  schedules: {
    schedule_id: number;
    title: string;
    driver_id?: number;
    driver_name?: string;
    frequency: string;
    is_active: boolean;
    last_run_at?: string;
    next_run_at?: string;
    total_jobs_created: number;
    success_jobs: number;
    failed_jobs: number;
    recent_jobs: { job_id: string; status: string; created_at: string; error?: string }[];
  }[];
  total_schedules: number;
}

export interface DriverPerformance {
  driver_id: number;
  driver_name: string;
  national_code: string;
  status: string;
  total_jobs: number;
  success_jobs: number;
  failed_jobs: number;
  success_rate: number;
  last_job_at?: string;
}

export interface DashboardStats {
  client_id: number;
  total_drivers: number;
  active_drivers: number;
  total_plates: number;
  total_jobs: number;
  success_jobs: number;
  failed_jobs: number;
  pending_jobs: number;
  today_jobs: number;
  today_success: number;
  today_failed: number;
  success_rate: number;
}

export interface WaybillJobResponse extends WaybillJob {
  driver_name?: string;
}

export interface ClientStatsResponse extends ClientStats {}
