import { AuditAction } from '@prisma/client';
import { prisma } from '../lib/prisma.js';
import { logger } from '../lib/logger.js';

function msUntilNextTehranMidnight(timeZone: string): number {
  const now = new Date();
  const tehranNowString = now.toLocaleString('en-US', { timeZone });
  const tehranNow = new Date(tehranNowString);
  const next = new Date(tehranNow);
  next.setHours(24, 0, 0, 0);
  return next.getTime() - tehranNow.getTime();
}

export function startTehranMidnightCron(timeZone: string): void {
  const schedule = (): void => {
    const delay = msUntilNextTehranMidnight(timeZone);
    setTimeout(async () => {
      try {
        await prisma.$transaction([
          prisma.driver.updateMany({ data: { dailyAttempts: 0, dailySuccesses: 0 } }),
          prisma.auditLog.deleteMany({ where: { createdAt: { lt: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000) } } })
        ]);

        const summaries = await prisma.tenant.findMany({
          include: {
            jobs: {
              where: { createdAt: { gte: new Date(Date.now() - 24 * 60 * 60 * 1000) } }
            }
          }
        });

        for (const tenant of summaries) {
          const total = tenant.jobs.length;
          const success = tenant.jobs.filter((job: { status: string }) => job.status === 'SUCCESS').length;
          await prisma.auditLog.create({
            data: {
              tenantId: tenant.id,
              action: AuditAction.DAILY_SUMMARY_GENERATED,
              metadata: { total, success, date: new Date().toISOString() }
            }
          });
        }

        await prisma.auditLog.createMany({
          data: summaries.map((tenant: { id: string }) => ({
            tenantId: tenant.id,
            action: AuditAction.COUNTERS_RESET,
            metadata: { at: new Date().toISOString(), timezone: timeZone }
          }))
        });

        await prisma.$executeRawUnsafe('SELECT create_job_daily_partition(CURRENT_DATE);');
        await prisma.$executeRawUnsafe("SELECT create_job_daily_partition(CURRENT_DATE + interval '1 day');");
        await prisma.$executeRawUnsafe('SELECT drop_old_job_partitions(14);');
        logger.info('Tehran midnight cron completed');
      } catch (error) {
        logger.error({ error }, 'Tehran midnight cron failed');
      } finally {
        schedule();
      }
    }, delay);
  };

  schedule();
}
