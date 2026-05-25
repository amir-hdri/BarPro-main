declare module 'dotenv' {
  export function config(): void;
}

declare module 'zod' {
  export const z: any;
}

declare module 'pino' {
  const pino: any;
  export default pino;
}

declare module 'ioredis' {
  export default class IORedis {
    constructor(url: string, options?: Record<string, unknown>);
    get(key: string): Promise<string | null>;
    set(key: string, value: string, ...args: Array<string | number>): Promise<'OK'>;
    del(key: string): Promise<number>;
    ttl(key: string): Promise<number>;
    expire(key: string, seconds: number): Promise<number>;
    incr(key: string): Promise<number>;
    pexpire(key: string, ms: number): Promise<number>;
    ping(): Promise<string>;
    zadd(key: string, score: number, member: string): Promise<number>;
    hset(key: string, field: string, value: string): Promise<number>;
  }
}

declare module 'axios' {
  const axios: any;
  export default axios;
  export function isAxiosError(input: unknown): boolean;
}

declare module 'playwright' {
  export const chromium: any;
}

declare module 'prom-client' {
  export class Registry {
    contentType: string;
    metrics(): Promise<string>;
  }
  export function collectDefaultMetrics(input: { register: Registry }): void;
  export class Counter<T extends string = string> {
    constructor(input: any);
    labels(...args: string[]): { inc(value?: number): void };
  }
  export class Gauge<T extends string = string> {
    constructor(input: any);
    labels(...args: string[]): { set(value: number): void; inc(value?: number): void; dec(value?: number): void };
  }
  export class Histogram<T extends string = string> {
    constructor(input: any);
    startTimer(): () => void;
  }
}

declare module 'bullmq' {
  export type JobsOptions = any;
  export type Processor<T> = (job: { data: T }) => Promise<unknown>;
  export class Queue<T = unknown> {
    constructor(name: string, options: any);
    add(name: string, data: T, options?: any): Promise<void>;
    count(): Promise<number>;
  }
  export class QueueEvents {
    constructor(name: string, options: any);
  }
  export class Worker<T = unknown> {
    constructor(name: string, processor: Processor<T>, options: any);
    pause(): Promise<void>;
    resume(): Promise<void>;
    on(event: string, cb: (...args: any[]) => void): void;
  }
}

declare module '@prisma/client' {
  export enum PlanType {
    FREE = 'FREE',
    PRO = 'PRO',
    ENTERPRISE = 'ENTERPRISE'
  }
  export enum JobStatus {
    PENDING = 'PENDING',
    PROCESSING = 'PROCESSING',
    CAPTCHA_SOLVING = 'CAPTCHA_SOLVING',
    WAITING_AUTH = 'WAITING_AUTH',
    RETRY_SCHEDULED = 'RETRY_SCHEDULED',
    SUCCESS = 'SUCCESS',
    FAILED = 'FAILED',
    DEAD = 'DEAD'
  }
  export enum AuditAction {
    JOB_CREATED = 'JOB_CREATED',
    JOB_REQUEUED = 'JOB_REQUEUED',
    JOB_DEAD_LETTERED = 'JOB_DEAD_LETTERED',
    SESSION_REFRESHED = 'SESSION_REFRESHED',
    PROXY_ROTATED = 'PROXY_ROTATED',
    COUNTERS_RESET = 'COUNTERS_RESET',
    DAILY_SUMMARY_GENERATED = 'DAILY_SUMMARY_GENERATED'
  }
  export type JobKind = 'SUBMIT' | 'AUTH_REFRESH';
  export class PrismaClient {
    tenant: any;
    driver: any;
    job: any;
    auditLog: any;
    $connect(): Promise<void>;
    $disconnect(): Promise<void>;
    $transaction(input: any): Promise<any>;
    $queryRaw(input: TemplateStringsArray): Promise<any>;
    $executeRawUnsafe(sql: string): Promise<any>;
  }
}

declare module 'jsonwebtoken' {
  export function verify(token: string, secret: string, options?: Record<string, unknown>): any;
  export function sign(payload: Record<string, unknown>, secret: string, options?: Record<string, unknown>): string;
}
