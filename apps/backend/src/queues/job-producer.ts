import { JobStatus, type JobKind } from '@prisma/client';
import { prisma } from '../lib/prisma.js';
import { authQueue, deadLetterQueue, retryQueue, submitQueue, type AuthJobData, type DeadLetterJobData, type RetryJobData, type SubmitJobData } from './bullmq.js';

export class JobProducer {
  public async enqueueSubmit(data: SubmitJobData): Promise<void> {
    await submitQueue.add(`submit:${data.jobId}`, data, { jobId: data.jobId });
  }

  public async enqueueAuth(data: AuthJobData): Promise<void> {
    await authQueue.add(`auth:${data.driverId}`, data, {
      jobId: `${data.driverId}:${data.reason}`
    });
  }

  public async enqueueRetry(data: RetryJobData, delayMs: number): Promise<void> {
    await retryQueue.add(`retry:${data.target}:${data.driverId}:${Date.now()}`, data, { delay: delayMs });
  }

  public async moveToDeadLetter(data: DeadLetterJobData): Promise<void> {
    await deadLetterQueue.add(`dlq:${data.correlationId}`, data);
    if (data.jobId) {
      await prisma.job.update({ where: { id: data.jobId }, data: { status: JobStatus.DEAD, lastError: data.detail } });
    }
  }

  public async createAuditLog(tenantId: string, action: string, metadata: Record<string, unknown>, jobId?: string, driverId?: string): Promise<void> {
    await prisma.auditLog.create({
      data: {
        tenantId,
        action,
        metadata,
        ...(jobId ? { jobId } : {}),
        ...(driverId ? { driverId } : {})
      }
    });
  }
}
