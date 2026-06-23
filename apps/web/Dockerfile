FROM node:20-slim AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

RUN addgroup --system --gid 1001 nodejs \
 && adduser  --system --uid 1001 nextjs

# فایل‌های بیلد شده از قبل آپلود شده‌اند (بیلد روی Mac انجام می‌شود)
COPY public               ./public
COPY .next/static         ./.next/static
COPY .next/standalone/.   ./

RUN mkdir -p .next && chown nextjs:nodejs .next

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
