# راهنمای جامع و فنی Vercel (آموزش کامل از صفر تا Migration)

> یک مرجع کامل و تخصصی برای پلتفرم Vercel — شامل معماری، Functions، Fluid Compute، Edge،
> Next.js، AI SDK / AI Gateway، Storage، CLI، Routing، Security، Observability، Multi-tenant،
> Templates، PPR، Build Output API و الگوهای Migration.
> منابع: vercel.com/docs، Knowledge Base، Templates، nextjs.org/learn، کاتالوگ AI Gateway.
> تاریخ بازبینی مستندات: project-config 2026-06، functions 2026-07، KB 2025-11، Prisma 2026-05.

---

## فهرست مطالب

1. مدل ذهنی پلتفرم
2. Vercel Functions (Serverless Core)
3. Fluid Compute (تحلیل عمیق)
4. Edge Runtime در مقابل Node.js
5. Streaming (جریان‌سازی)
6. Next.js روی Vercel
7. PPR (Partial Prerendering)
8. زیرساخت AI — AI SDK
9. AI Gateway (تحلیل کامل)
10. ادغام Google AI / Gemini
11. سایر بلوک‌های AI (v0, MCP, eve, Sandbox)
12. Storage (ذخیره‌سازی)
13. پیکربندی پروژه (vercel.json / vercel.ts)
14. Build Output API
15. Routing (Middleware / Rewrites / Redirects)
16. Security (Firewall / WAF / Bot Management)
17. Observability (مشاهده‌پذیری)
18. اجرای پس‌زمینه و دائمی (Cron / Queues / Workflows)
19. Multi-tenant Platforms
20. Feature Flags
21. CLI (خط فرمان)
22. Templates (الگوها)
23. Headless CMS (WordPress / Contentful / Shopify)
24. Fullstack DB Pattern (Prisma Postgres)
25. Next.js Learn
26. یادداشت درباره "Antigram / Gravity"
27. نکات تخصصی (Gotchas)
28. راهنمای Migration اختصاصی BarPro
29. مقایسه هزینه و معماری (Bonus)
30. چک‌لیست عملیاتی

---

## ۱ — مدل ذهنی پلتفرم (Platform Mental Model)

Vercel یک **Frontend Cloud** است: تمام چرخه‌ی ساخت (build)، تست، استقرار (deploy)، مقیاس‌پذیری
(scale) و امن‌سازی اپلیکیشن‌های وب را مدیریت می‌کند **بدون اینکه شما سروری را مدیریت کنید**.

### ۱.۱ مفاهیم بنیادی

| مفهوم | توضیح |
|-------|-------|
| **Deployment** | خروجی یک build موفق؛ هر کدام یک URL یکتا دارند (مثل `myapp-abc123.vercel.app`) |
| **Preview Deployment** | نسخه‌ای که برای هر Pull Request ساخته می‌شود — برای تست قبل از ادغام |
| **Production Deployment** | نسخه‌ای که روی دامنه‌ی اصلی سرویس می‌دهد |
| **Edge Network** | شبکه‌ی توزیع‌شده‌ی جهانی Vercel (۱۸+ منطقه) |
| **Build Cache** | کش هوشمند بین buildها برای سرعت بیشتر |

### ۱.۲ چرخه‌ی یک درخواست (Request Lifecycle)

```
کاربر ──HTTPS──> Edge CDN (نزدیک‌ترین نقطه)
                    │
        ┌───────────┼───────────────────────────┐
        │           │                           │
    فایل استاتیک   Middleware (قبل از کش)    Function (region مشخص)
   (سرویس سریع)    (auth/rewrite)            (Node/Python/Edge)
```

### ۱.۳ روش‌های استقرار (Deploy Triggers)

1. **Git Integration:** اتصال GitHub / GitLab / Bitbucket / Azure DevOps. هر push → build خودکار.
2. **Vercel CLI:** `vercel deploy` در ترمینال (مناسب تست محلی قبل از commit).
3. **Vercel Drop:** کشیدن و رها کردن (drag & drop) یک پوشه در مرورگر — نیازی به Git ندارد.
4. **Deploy Hooks:** یک URL یکتا که با یک درخوان HTTP (مثلاً از CI/CD خودتان) استقرار را تریگر می‌کند.
5. **REST API:** ارسال POST به endpoint استقرار برای اتوماسیون پیشرفته.

**چرا Vercel فرق دارد؟** چون *framework-aware* است. وقتی تشخیص می‌دهد پروژه Next.js / Nuxt /
SvelteKit است، تنظیمات build، routing و caching را **خودکار** بهینه می‌کند — برخلاف سرویس‌های
عمومی مثل AWS که همه‌چیز را دستی تنظیم می‌کنید.

---

## ۲ — Vercel Functions (هسته‌ی محاسبات Serverless)

Functions واحدهای اجرایی شما روی Vercel هستند. هر endpoint API معادل یک Function است.

### ۲.۱ تعریف یک Function

در Next.js (App Router):
```ts
// app/api/hello/route.ts
import { NextRequest } from 'next/server';

export async function GET(request: NextRequest) {
  return Response.json({ message: 'Hello from Vercel Function' });
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  return Response.json({ received: body });
}
```

در فریم‌ورک‌های دیگر یا raw:
```ts
// api/hello.ts
export default function handler(request: Request) {
  return new Response('Hello');
}
```

### ۲.۲ چرخه حیات (Lifecycle)

- هر درخواست = یک **invocation** (فراخوانی) جدید.
- اگر ترافیک ادامه داشته باشد، **نمونه‌های گرم (warm instances)** دوباره استفاده می‌شوند
  (cold start فقط برای اولین بار یا بعد از بیکاری).
- وقتی ترافیک قطع شود → **scale-to-zero** (هزینه صفر).
- هیچ سروری برای مدیریت وجود ندارد؛ Vercel مقیاس‌بندی را انجام می‌دهد.

### ۲.۳ Multi-runtime (چند زبان)

| Runtime | نحوه انتخاب | کاربرد |
|---------|-------------|--------|
| Node.js | پیش‌فرض یا `export const runtime = 'nodejs'` | اکثر اپلیکیشن‌ها |
| Python | پسوند `.py` یا `runtime = 'python'` | ML / اسکریپت‌های داده |
| Go | پسوند `.go` | عملکرد بالا |
| Bun | `runtime = 'bun'` | جایگزین سریع Node |
| Rust | پسوند `.rs` | سیستمی / عملکرد بحرانی |
| Edge | `runtime = 'edge'` | کم‌تأخیر نزدیک کاربر |

### ۲.۴ پیکربندی هر Function

```ts
// app/api/heavy/route.ts
export const runtime = 'nodejs';          // یا 'edge'
export const maxDuration = 60;            // حداکثر زمان اجرا (محدود به پلن)
export const preferredRegion = ['iad1'];  // منطقه‌ی اجرا
export const dynamic = 'force-dynamic';   // جلوگیری از کش شدن
```

یا در `vercel.json`:
```json
{
  "functions": {
    "app/api/heavy/route.ts": {
      "memory": 1024,
      "maxDuration": 60,
      "runtime": "nodejs20.x"
    }
  }
}
```

---

## ۳ — Fluid Compute (تحلیل عمیق)

Fluid Compute یک **مدل اجرایی جدید** است که از ۲۰۲۵-۰۴-۲۳ پیش‌فرض پروژه‌های جدید است. ترکیبی از
انعطاف‌پذیری serverless و ظرفیت شبیه‌به‌سرور (server-like capacity).

### ۳.۱ چرا ساخته شد؟

در مدل serverless کلاسیک، هر درخواست یک پروسه/محیط ایزوله می‌گرفت → هزینه‌ی بالا برای کارهای
I/O-bound (مثل صدا زدن دیتابیس یا LLM). Fluid Compute اجازه می‌دهد **چندین درخواست هم‌زمان روی
یک نمونه** اجرا شوند — مثل یک سرور معمولی اما بدون نیاز به مدیریت آن.

### ۳.۲ فعال‌سازی

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "fluid": true
}
```

Runtimes پشتیبانی‌شده: Node.js, Python, Edge, Bun, Rust.

### ۳.۳ ویژگی‌های کلیدی

**الف) Optimized Concurrency (هم‌زمانی بهینه):**
چندین invocation روی یک instance اجرا می‌شوند. برای:
- جستجوهای embedding (vector similarity)
- پرس‌وجوهای vector DB (مثل Pinecone / pgvector)
- فراخوانی APIهای خارجی (LLMها، پرداخت و غیره)

این یعنی هزینه‌ی زیرساخت برای کارهای I/O-bound به‌شدت کم می‌شود.

**ب) Background Processing (پردازش پس‌زمینه):**
```ts
import { waitUntil } from '@vercel/functions';

export async function POST(req: Request) {
  const data = await req.json();
  // پاسخ را سریع برمی‌گردانیم
  const response = Response.json({ ok: true });
  // کارهای سنگین بعد از ارسال پاسخ
  waitUntil(async () => {
    await sendAnalytics(data);
    await logToDatabase(data);
  });
  return response;
}
```
`waitUntil` اجازه می‌دهد کارهای غیرضروری (لاگ، آنالیتیکس، نوتیفیکیشن) بعد از ارسال پاسخ انجام
شوند بدون اینکه کاربر منتظر بماند.

**ج) Cold-start Optimization:**
بهینه‌سازی خودکار bytecode + پیش‌گرم‌کردن (pre-warming) در محیط تولید → اولین درخواست سریع‌تر.

**د) Failover هوشمند:**
1. ابتدا به **Availability Zone (AZ)** دیگر در همان منطقه.
2. اگر نشد، به **نزدیک‌ترین منطقه‌ی بعدی**.
این برای هر دو حالت fluid و non-fluid اعمال می‌شود (در سطح zone).

**ه) Error Isolation (ایزولاسیون خطا):**
اگر یک درخواست خطای مدیریت‌نشده بدهد، بقیه‌ی درخواست‌های هم‌زمان روی آن instance **نمی‌ریزند**.

### ۳.۴ مدل قیمت‌گذاری (Active CPU)

Fluid Compute از مدل **Active CPU** استفاده می‌کند: فقط زمانی که CPU واقعاً در حال پردازش است
هزینه می‌شود — نه زمانی که منتظر پاسخ شبکه (I/O) است. این برای کارهای I/O-bound بسیار به‌صرفه است.

---

## ۴ — Edge Runtime در مقابل Node.js

| ویژگی | Edge | Node.js |
|-------|------|---------|
| محل اجرا | نزدیک‌ترین منطقه به کاربر | منطقه‌ی انتخابی (ثابت) |
| زمان شروع پاسخ | ۲۵ ثانیه | طولانی‌تر (بسته به پلن) |
| حداکثر stream | ۳۰۰ ثانیه | بسته به پلن (تا ۹۰۰s در Enterprise) |
| APIهای موجود | زیرمجموعه‌ی Web Standard | تمام APIهای Node.js |
| ماژول‌های native | محدود | کامل |
| مناسب برای | منطق سبک، کم‌تأخیر (rewrite/auth) | اکثر اپلیکیشن‌ها، ML، DB |

**توصیه‌ی Vercel:** Edge را به Node.js مهاجرت دهید — عملکرد و پایداری بهتر، هر دو روی Fluid
Compute با قیمت‌گذاری Active CPU اجرا می‌شوند.

مثال مهاجرت Edge → Node:
```ts
// قبل
export const runtime = 'edge';
// بعد
export const runtime = 'nodejs';
// (بقیه کد بدون تغییر اگر از Web Standard APIs استفاده کرده باشید)
```

---

## ۵ — Streaming (جریان‌سازی)

ایده: سرور داده را به **تکه‌های کوچک (chunk)** می‌فرستد به محض آماده شدن. کلاینت تدریجاً رندر
می‌کند → زمان درک‌شده‌ی (perceived) بارگذاری کمتر.

### ۵.۱ چرا مهم است؟
- **Ecommerce:** محصولات مهم زودتر نمایش داده می‌شوند.
- **AI:** متن پاسخ LLM کلمه‌به‌کلمه نمایش می‌شود (مثل چت‌بات‌ها).

### ۵.۲ مثال raw (بدون فریم‌ورک)
```ts
// app/api/stream/route.ts
export async function GET() {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      for (const chunk of ['یک', 'دو', 'سه']) {
        controller.enqueue(encoder.encode(chunk + '\n'));
        await new Promise(r => setTimeout(r, 200));
      }
      controller.close();
    },
  });
  return new Response(stream, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
```

### ۵.۳ مثال با AI SDK (backpressure خودکار)
```ts
import { streamText } from 'ai';
export async function POST(req: Request) {
  const { messages } = await req.json();
  const result = streamText({
    model: 'anthropic/claude-sonnet-4.5',
    system: 'You are a helpful assistant.',
    messages,
  });
  return result.toUIMessageStreamResponse();
}
```
AI SDK **backpressure** (فشار معکوس — وقتی کلاینت کندتر از سرور است) را خودکار مدیریت می‌کند
و از پر شدن حافظه جلوگیری می‌کند.

---

## ۶ — Next.js روی Vercel (Framework-aware)

Next.js فریم‌ورک fullstack React ساخته‌ی خود Vercel است. استقرار روی Vercel **zero-config** است
و ویژگی‌های زیرساختی اضافه می‌کند.

### ۶.۱ ISR (Incremental Static Regeneration)
به‌روزرسانی محتوا بدون بازسازی کل سایت:
```ts
// app/blog/page.tsx (Server Component)
export default async function Page() {
  const posts = await fetch('https://api.vercel.app/blog', {
    next: { revalidate: 10 }, // هر ۱۰ ثانیه یک‌بار چک کن
  }).then(r => r.json());
  return <BlogList posts={posts} />;
}
```
**تفاوت با self-hosted:** روی Vercel کش CDN جهانی + zero-downtime + انتشار ~۳۰۰ms + ذخیره‌ی
**دائمی** (durable) دارد. در self-hosted ISR تک‌منطقه‌ای و کش موقتی است (با restart از دست می‌رود).

### ۶.۲ SSR (Server-Side Rendering)
از طریق Functions رندر می‌شود؛ scale-to-zero + auto-scale + Cache-Control خودکار شامل
`stale-while-revalidate`.

### ۶.۳ Data Cache
کش کردن در سطح کامپوننت با `revalidate` که **بین deployها باقی می‌ماند** (persist).

### ۶.۴ Server Actions
فرم‌ها و جهش‌های داده بدون ساخت API دستی:
```ts
// app/actions.ts
'use server';
export async function createPost(formData: FormData) {
  const title = formData.get('title');
  // ذخیره در دیتابیس
}
```

---

## ۷ — PPR (Partial Prerendering)

یک مدل رندرینگ جدید (experimental در Next 14+) که **پوسته‌ی استاتیک** را از edge سرویس می‌دهد
و **حفره‌های داینامیک** را با `<Suspense>` stream می‌کند.

```jsx
// app/page.tsx
export default function Page() {
  return (
    <main>
      <StaticHeader />           {/* استاتیک — سریع از edge */}
      <Suspense fallback={<Skeleton />}>
        <DynamicContent />       {/* داینامیک — stream می‌شود */}
      </Suspense>
    </main>
  );
}
```
```js
// next.config.js
experimental: { ppr: true }
```
**مزایا:** TTI (Time To Interactive) کمتر، تجربه‌ی کاربری بهتر، ترکیب ISR + SSR.

برای BarPro: داشبورد ادمین را با PPR بسازید — هدر و سایدبار استاتیک، جدول jobs داینامیک.

---

## ۸ — زیرساخت AI — AI SDK

ابزار TypeScript برای ساخت اپلیکیشن‌های AI. `npm i ai`.

```ts
import { generateText, generateObject, streamText } from 'ai';

// تولید متن ساده
const { text } = await generateText({
  model: 'openai/gpt-5.2',
  prompt: 'توضیح بده چطور SSL کار می‌کند',
});

// خروجی ساختاریافته (Structured Output)
const { object } = await generateObject({
  model: 'anthropic/claude-sonnet-4.5',
  schema: z.object({ name: z.string(), age: z.number() }),
  prompt: 'نام و سن علی را استخراج کن',
});

// استریمینگ
const result = streamText({ model: 'openai/gpt-5.2', prompt: '...' });
```

**قابلیت‌ها:** unified provider API (تعویض مدل در ۲ خط)، structured outputs
(`generateObject`/`streamObject`)، tool calling، streaming-first. سازگار با AI SDK v5/v6.

---

## ۹ — AI Gateway (تحلیل کامل)

یک **endpoint واحد** برای صدها مدل با بودجه، failover و مانیتورینگ متمرکز.

### ۹.۱ سازگاری
- AI SDK v5/v6
- OpenAI Chat Completions API
- OpenAI Responses API
- Anthropic Messages API
- یا فریم‌ورک خودتان

### ۹.۲ مُدالیتی‌ها (Modalities)
متن (text)، تصویر (image)، ویدیو (beta)، realtime (beta)، speech-to-text (beta)،
text-to-speech (beta)، embeddings، reranking.

### ۹.۳ کنترل‌ها (Controls)
| کنترل | توضیح |
|-------|-------|
| BYOK | Bring Your Own Key — کلید مدل را خودتان می‌دهید |
| Zero Data Retention | داده‌ها نگه‌داری نمی‌شوند |
| Disallow Prompt Training | جلوگیری از آموزش مدل با داده‌های شما |
| Provider Allowlist | فقط ارائه‌دهندگان مجاز |
| Model Allowlist | فقط مدل‌های مجاز |
| Regional Inference | استنتاج در منطقه‌ی مشخص |
| Model Fallbacks | اگر مدل اصلی خطا داد، مدل دیگر |
| Automatic Caching | کش خودکار پاسخ‌های مشابه |
| Fast Mode | حالت سریع (beta) |
| Service Tiers | سطوح سرویس |

### ۹.۴ ادغام با ایجنت‌های کدینگ
Claude Code، OpenAI Codex، Roo Code، Cline، Blackbox AI، Crush، Grok Build، **Hermes**،
OpenCode، Superset، Conductor و غیره — همه از طریق AI Gateway متصل می‌شوند.

### ۹.۵ مثال استفاده
```ts
import { generateText } from 'ai';
import { gateway } from '@ai-sdk/gateway'; // یا پیکربندی baseURL

const { text } = await generateText({
  model: gateway('anthropic/claude-sonnet-4.5'),
  prompt: '...',
});
```

---

## ۱۰ — ادغام Google AI / Gemini (کامل)

Gemini مدل‌های Google هستند که در AI Gateway و AI SDK **first-class** هستند.

### ۱۰.۱ روش الف — از طریق AI Gateway (توصیه‌شده)
```ts
import { generateText } from 'ai';
const { text } = await generateText({
  model: 'google/gemini-2.5-pro',  // یا gemini-2.5-flash، gemini-2.0-flash
  prompt: 'خلاصه‌ی این سند را بنویس',
  // کلید از env: GOOGLE_API_KEY یا Vercel AI Gateway key
});
```
مزیت: Gateway مدیریت بودجه، failover و مانیتورینگ را اضافه می‌کند.

### ۱۰.۲ روش ب — Google SDK مستقیم (Node.js runtime)
```ts
// app/api/gemini/route.ts
import { GoogleGenerativeAI } from '@google/generative-ai';

const genAI = new GoogleGenerativeAI(process.env.GOOGLE_API_KEY!);

export async function POST(req: Request) {
  const model = genAI.getGenerativeModel({ model: 'gemini-2.5-flash' });
  const { prompt } = await req.json();
  const result = await model.generateContent(prompt);
  return Response.json({ text: result.response.text() });
}
```

### ۱۰.۳ روش ج — Streaming با AI SDK
```ts
import { streamText } from 'ai';
import { google } from '@ai-sdk/google';

export async function POST(req: Request) {
  const { messages } = await req.json();
  const result = streamText({ model: google('gemini-2.5-flash'), messages });
  return result.toUIMessageStreamResponse();
}
```

### ۱۰.۴ نکات حیاتی
- SDK رسمی `@google/generative-ai` **فقط روی Node.js runtime** کار می‌کند (به APIهای Node نیاز دارد).
- Edge runtime فقط `google()` provider از AI SDK را برای streaming پشتیبانی می‌کند (نه کل SDK).
- کلید `GOOGLE_API_KEY` را **فقط سرور-ساید** در Environment Variables نگه دارید؛ هرگز به کلاینت ندهید.
- برای حجم بالا: AI Gateway را ترجیح دهید تا بودجه، failover و rate limit متمرکز باشند.

---

## ۱۱ — سایر بلوک‌های AI

- **v0:** دستیار تولید UI مبتنی بر AI (از توصیف متنی → کامپوننت React).
- **MCP Servers:** سرورهایی که ابزار (tools) را برای ایجنت‌ها فراهم می‌کنند.
- **eve:** فریم‌ورک filesystem-first برای ایجنت‌های backend دائمی.
- **Sandbox:** اجرای کد نامطمئن در محیط ایزوله و موقت (ephemeral).

---

## ۱۲ — Storage (ذخیره‌سازی)

| محصول | کاربرد | زمان خواندن | زمان نوشتن |
|-------|--------|-------------|-------------|
| **Blob** | فایل‌های بزرگ (تصویر/ویدیو/آواتار) | سریع | میلی‌ثانیه |
| **Global Config** | کانفیگ کم‌تأخیر (مثل فلگ‌ها) | <1ms (۹۹٪ <10ms) | ثانیه |
| **Marketplace** | Postgres (Neon/Prisma)، Redis (Upstash)، NoSQL، Vector | — | — |

### ۱۲.۱ نمونه Blob
```ts
import { put, list, del } from '@vercel/blob';
const { url } = await put('avatar.png', file, { access: 'public' });
```

### ۱۲.۲ نکته‌ی معماری
دیتابیس را در **همان منطقه‌ی Functions** بگذارید تا latency کم شود. داده‌های پرتکرار را با
cache headers / ISR روی CDN کش کنید تا round-trip کم شود.

---

## ۱۳ — پیکربندی پروژه (vercel.json / vercel.ts)

فقط **یکی** را استفاده کنید (نه هر دو):

### ۱۳.۱ vercel.json (استاتیک)
```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "framework": "nextjs",
  "fluid": true,
  "regions": ["iad1"],
  "headers": [
    {
      "source": "/(.*)",
      "headers": [{ "key": "X-Content-Type-Options", "value": "nosniff" }]
    }
  ],
  "rewrites": [{ "source": "/api/:path*", "destination": "https://api.example.com/:path*" }]
}
```

### ۱۳.۲ vercel.ts (پویا در زمان build)
```ts
import { defineConfig } from 'vercel';
export default defineConfig({
  framework: 'nextjs',
  fluid: true,
  // می‌توانید از env یا API call برای تولید پویا استفاده کنید
  regions: process.env.REGION ? [process.env.REGION] : ['iad1'],
});
```

### ۱۳.۳ جدول کامل پراپرتی‌ها
`buildCommand`, `devCommand`, `installCommand`, `outputDirectory`, `framework`, `bunVersion`,
`fluid`, `functions`, `crons`, `regions`, `functionFailoverRegions`, `headers`, `redirects`,
`rewrites`, `bulkRedirectsPath`, `trailingSlash`, `cleanUrls`, `images`, `ignoreCommand`, `public`.

---

## ۱۴ — Build Output API

مشخصات ساختار فایل‌سیستم `.vercel/output` که build شما تولید می‌کند (framework-defined infrastructure).

### ۱۴.۱ Static Files
`.vercel/output/static` → توسط Edge CDN سرویس می‌شود، در ریشه‌ی URL نگاشت می‌شود.
**Immutable static:** `.vercel/output/static/_vercel/immutable/` + `immutable.json` (مانیفست
hash کامل) → بین deployها مشترک است (بدون `?dpl`)، کش‌کردن cross-deployment بهتر.

### ۱۴.۲ Functions
`.vercel/output/functions/<name>.func/` + `.vc-config.json` (handler, runtime, memory, maxDuration).
پسوند `.func` از URL حذف می‌شود (`api/posts.func` → `/api/posts`). فایل‌های private داخل `.func`
برای کاربر در دسترس نیستند اما توسط کد Function قابل استفاده‌اند.

### ۱۴.۳ محدودیت
وابستگی‌های native حتماً روی **Linux x64** ساخته شوند (مطابق Build Image).

---

## ۱۵ — Routing (مسیریابی)

### ۱۵.۱ Middleware
```ts
// middleware.ts
import { NextResponse } from 'next/server';
export function middleware(req: Request) {
  const token = req.headers.get('authorization');
  if (!token) return NextResponse.redirect(new URL('/login', req.url));
  return NextResponse.next();
}
export const config = { matcher: ['/dashboard/:path*'] };
```
⚠️ Middleware **قبل از کش** اجرا می‌شود ⇒ **نمی‌تواند** `cache-control` تنظیم کند.

### ۱۵.۲ Rewrites (بدون تغییر URL)
```json
{
  "rewrites": [
    { "source": "/api/:path*", "destination": "https://api.example.com/:path*" }
  ]
}
```
دو نوع:
- **داخل‌برنامه‌ای:** URLهای دوستانه، A/B testing، مسیریابی کشوری با `x-vercel-ip-country`.
- **خارجی:** reverse proxy، ترکیب backendها، microfrontends، کش API خارجی.

کش کردن rewrites خارجی: `CDN-Cache-Control` / `Vercel-CDN-Cache-Control` را رعایت می‌کند
(پیش‌فرض روشن برای پروژه‌های ساخته‌شده ≥ 2026-04-06، یا با هدر `x-vercel-enable-rewrite-caching`).

### ۱۵.۳ Redirects
۳xx با تغییر URL. `/.well-known` رزرو شده و قابل rewrite/redirect نیست (فقط Enterprise برای SSL سفارشی).

---

## ۱۶ — Security (امنیت)

### ۱۶.۱ لایه‌های Firewall (به ترتیب اجرا)
1. **Platform-wide DDoS mitigation** [همه پلن‌ها]
2. **WAF IP blocking**
3. **WAF custom rules**
4. **WAF Managed Rulesets**

### ۱۶.۲ WAF
قوانین سفارشی، rate limiting (از طریق SDK)، IP blocking، Managed Rulesets، Attack Mode.

### ۱۶.۳ Bot Management / BotID
CAPTCHA نامرئی بدون چالش برای کاربر واقعی.

### ۱۶.۴ سایر
- **Deployment Protection:** محدود کردن دسترسی به استقرارها/پیش‌نمایش‌ها.
- **RBAC:** کنترل دسترسی مبتنی بر نقش.
- **JA3/JA4:** شناسایی کلاینت از اثر انگشت TLS.
- **AI Gateway governance:** Zero Data Retention + Provider/Model Allowlist.

---

## ۱۷ — Observability (مشاهده‌پذیری)

### ۱۷.۱ Insights
Functions، External APIs، Edge Requests، Middleware، Fast Data Transfer، Image Optimization،
ISR، Blob، Build Diagnostics، AI Gateway، Queues، Microfrontends.

### ۱۷.۲ ابزارها
Runtime Logs، Tracing (instrumentation + session)، Speed Insights (Core Web Vitals)، Web Analytics،
Notebooks (کوئری‌های ذخیره‌شده)، Drains (خروجی به S3/Splunk/Panther).

---

## ۱۸ — اجرای پس‌زمینه و دائمی

### ۱۸.۱ Cron Jobs
در `vercel.json`:
```json
{
  "crons": [
    { "path": "/api/cron/cleanup", "schedule": "0 2 * * *" }
  ]
}
```
Vercel یک HTTP GET به URL شما می‌زند. هدرها: `x-vercel-cron-schedule`، UA `vercel-cron/1.0`.
فرمت cron: ۵ فیلد (دقیقه/ساعت/روز-ماه/ماه/روز-هفته).

### ۱۸.۲ Queues (Beta)
جریان رویداد دائمی؛ موتور پشت Workflows.

### ۱۸.۳ Workflows
اجرای دائمی JS/TS/Python با `'use workflow'`:
```ts
export async function aiContentWorkflow(topic: string) {
  'use workflow';
  const draft = await generateDraft(topic);
  const summary = await summarizeDraft(draft);
  return { draft, summary };
}
```
ویژگی‌ها: Resumable (توقف/ادامه از دقیقه تا ماه)، Durable (از crash با replay قطعی جان می‌دهد)،
Observable. هر اجرا در یک منطقه پین می‌شود.

---

## ۱۹ — Multi-tenant Platforms (Vercel for Platforms)

### ۱۹.۱ Wildcard Domains
`*.acme.com`: اشاره NS به `ns1.vercel-dns.com` / `ns2.vercel-dns.com`؛ Vercel SSL را روی هر
ساب‌دامنه خودکار می‌سازد.

### ۱۹.۲ Custom Domains (برنامه‌نویسی‌شده)
```ts
import { VercelCore as Vercel } from '@vercel/sdk/core.js';
import { projectsAddProjectDomain } from '@vercel/sdk/funcs/projectsAddProjectDomain.js';

const vercel = new Vercel({ bearerToken: process.env.VERCEL_TOKEN });
await projectsAddProjectDomain(vercel, {
  idOrName: 'my-app',
  teamId: 'team_1234',
  requestBody: { name: 'tenant.com' },
});
```

### ۱۹.۳ Platforms Starter Kit
Next.js 15 + React 19 + Upstash Redis + Tailwind 4 + shadcn/ui. مسیریابی ساب‌دامنه از طریق
middleware، رابط ادمین، مدیریت tenantها.

---

## ۲۰ — Feature Flags

- **Vercel Flags (native):** قوانین هدف‌گذاری، بخش‌ها (segments)، splitها، کنترل محیط.
- **Marketplace:** LaunchDarkly، Statsig، Split (از طریق داشبورد یکپارچه).
- **Flags Explorer:** مشاهده/تغییر فلگ‌ها از Toolbar در زمان توسعه.
- **Flags SDK:** native برای Next.js/SvelteKit، TypeScript کامل.
- **Observability:** ارزیابی فلگ‌ها در Runtime Logs + تأثیر روی تبدیل (Web Analytics).

---

## ۲۱ — CLI (خط فرمان)

نصب: `pnpm i -g vercel`. در CI از `VERCEL_TOKEN` (env) استفاده کنید (ترجیح بر `--token`).

| دستور | کاربرد |
|-------|--------|
| `vercel deploy` | استقرار |
| `vercel dev` | سرور توسعه‌ی محلی |
| `vercel env` | pull/push متغیرهای محیطی |
| `vercel domains` / `vercel dns` | مدیریت دامنه |
| `vercel logs` / `vercel inspect` | مشاهده‌پذیری |
| `vercel rollback` | بازگشت فوری |
| `vercel link` / `vercel pull` | اتصال و کشیدن کانفیگ |
| `vercel crons` / `vercel flags` / `vercel firewall` | مدیریت ویژگی‌ها |
| `vercel blob` / `vercel mcp` / `vercel ai-gateway` | ابزارهای تخصصی |
| `vercel install` | provision کردن Marketplace (مثل دیتابیس) |

---

## ۲۲ — Templates (الگوها)

- **nextjs-commerce:** فروشگاه Shopify headless (RSC، Server Actions، Suspense، useOptimistic).
  با تغییر `lib/shopify` پشتیبانی از BigCommerce/Medusa/Saleor/Swell فعال می‌شود.
- **nextjs-boilerplate:** پایه‌ی create-next-app با فونت Geist.
- **platforms-starter-kit:** SaaS چندمستأجری با Redis.
- **cms-wordpress:** WordPress headless با WPGraphQL + ISR.
- **chatbot:** چت AI کامل.

---

## ۲۳ — Headless CMS

### ۲۳.۱ WordPress
نصب افزونه‌ی WPGraphQL؛ تنظیم `WORDPRESS_API_URL` در `.env.local`؛ fetch با `revalidate: 10`.
اگر WP خوابیده باشد → Vercel کش را سرویس می‌دهد؛ ISR در <۵۰۰ms منتشر می‌شود.

### ۲۳.۲ Contentful
Space ID + Content Management Token؛ کوئری/mutate GraphQL از سرور.

### ۲۳.۳ Shopify
Partner account → dev store → Storefront API token؛ `SHOPIFY_STOREFRONT_ACCESS_TOKEN` فقط
سرور-ساید.

---

## ۲۴ — Fullstack DB Pattern (Prisma Postgres)

۱. `create-next-app` → push به GitHub → import به Vercel.
۲. پنل Storage → Connect Database → Prisma → اضافه شدن `DATABASE_URL` (و `DIRECT_URL` اختیاری).
۳. `vercel env pull .env`.
۴. `npm i prisma @prisma/client @prisma/adapter-pg dotenv`؛ `postinstall: "prisma generate"`.
۵. `prisma/schema.prisma` + `prisma.config.ts`.
۶. `lib/prisma.ts` singleton با pg adapter؛ `npx prisma db push`.
۷. بارگذاری پست‌ها، Server Actions، drafts، deploy.

---

## ۲۵ — Next.js Learn

۱۶ فصل رایگان: Getting Started → CSS → Fonts/Images → Layouts → `<Link>` → DB → Fetching
(Server Components) → Static/Dynamic → Streaming → Search/Pagination → Mutating (Server Actions)
→ Errors → Accessibility → Auth (NextAuth.js) → Metadata → Next Steps.

---

## ۲۶ — یادداشت درباره "Antigram / Gravity"

محصول رسمی Vercel با نام **Antigram** یا **Gravity** وجود ندارد. سناریوها:
- اگر منظور **Antigravity CLI (`agy`)** باشد → ابزار orchestration ایجنت در محیط Hermes است (نه Vercel).
- اگر کدنام داخلی باشد → به عنوان ادغام سفارشی: rewrites + Workflows + Firewall + کلید سرور-ساید.
  برای ایجنت‌هایی که مدل صدا می‌زنند: از AI Gateway (شامل Gemini) استفاده کنید.

---

## ۲۷ — نکات تخصصی (Gotchas)

- Edge → Node.js مهاجرت دهید (عملکرد/پایداری).
- Middleware قبل از کش؛ نمی‌تواند cache-control بگذارد.
- ISR self-hosted ≠ ISR روی Vercel (تک‌منطقه + موقتی).
- External rewrites روی پروژه‌های قدیمی کش نمی‌شوند (opt-in).
- `/.well-known` قابل rewrite نیست (فقط Enterprise SSL سفارشی).
- `vercel.ts` و `vercel.json` متقابلاً انحصاری.
- Fluid Compute پیش‌فرض جدید (۲۰۲۵-۰۴-۲۳+).
- وابستگی native حتماً روی Linux x64.
- Gemini SDK رسمی ⇒ Node.js runtime.

---

## ۲۸ — راهنمای Migration اختصاصی BarPro

BarPro: RPA چندمستأجری (Next.js 15 فرانت‌اند؛ FastAPI + Celery + PostgreSQL + Redis بک‌اند؛
۱۳ tenant؛ سرور تکی، دو IP).

### ۲۸.۱ نقشه‌برداری (Mapping)

| لایه BarPro | معادل Vercel | استراتژی |
|------------|--------------|----------|
| Next.js 15 (فرانت‌اند) | Vercel Native | Deploy مستقیم، zero-config |
| FastAPI (بک‌اند) | Vercel Functions + Fluid Compute | Re-platform یا rewrite پشت |
| Celery Workers (RPA) | Workflows / Queues یا هاست خارجی | نگه‌داشتن پشت rewrite |
| PostgreSQL (SQLModel) | Neon / Prisma Postgres | Marketplace، هم‌منطقه |
| Redis (Cache/Queue) | Upstash Redis + Queues | Marketplace |
| Nginx (Reverse Proxy) | Vercel Edge / Rewrites | جایگزینی |
| Squid (Proxies) | خارجی یا Container Images | حفظ برای RPA |

### ۲۸.۲ گام‌به‌گام
۱. **فرانت‌اند:** deploy مستقیم. PPR برای داشبورد + Feature Flags برای عرضه مرحله‌ای.
۲. **بک‌اند:** یا re-platform روی Functions + Fluid Compute، یا نگه‌داشتن FastAPI پشت rewrite
   (reverse proxy به سرور موجود). Playwright (اتوماسیون مرورگر) به مرورگر واقعی و session طولانی
   نیاز دارد → بهتر روی هاست worker جداگانه بماند یا از Container Images/Sandbox استفاده شود.
۳. **PostgreSQL:** Neon/Prisma Postgres از Marketplace؛ هم‌منطقه با Functions؛ SQLModel را نگه دارید،
   connection string را به `DATABASE_URL` اشاره دهید.
۴. **Redis/Celery:** Upstash Redis + Queues، یا پشت rewrite.
۵. **Multi-tenancy:** الگوی Platforms Starter Kit (ساب‌دامنه با middleware + Redis) + Vercel SDK برای دامنه‌های سفارشی.
۶. **AI:** برای حل CAPTCHA از طریق LLM → AI Gateway (شامل Gemini) برای بودجه/failover.
۷. **امنیت:** قوانین WAF + Bot Management + Deployment Protection را بازسازی کنید (حفظ rate limiter fail-closed).

---

## ۲۹ — مقایسه هزینه و معماری (Bonus)

### ۲۹.۱ Vercel در مقابل Self-hosted (BarPro فعلی)
| معیار | Self-hosted فعلی | Vercel |
|-------|------------------|--------|
| مدیریت سرور | دستی (۱۳ کانتینر) | صفر |
| مقیاس‌پذیری | محدود به ۴ vCPU | خودکار، جهانی |
| CDN | ندارد | جهانی |
| هزینه در بیکاری | ۴ vCPU + ۱۲GB | صفر (scale-to-zero) |
| نگهداری RPA | ساده‌تر (کنترل کامل) | نیاز به rewrite/Container |

### ۲۹.۲ توصیه
معماری ترکیبی (Hybrid): فرانت‌اند + APIهای سبک → Vercel؛ RPA Worker (Playwright/Squid) →
همچنان روی سرور اختصاصی پشت rewrite. این بیشترین بهره‌وری را بدون بازنویسی کامل لایه‌ی RPA می‌دهد.

---

## ۳۰ — چک‌لیست عملیاتی

- [ ] پروژه Next.js را به Vercel import کنید.
- [ ] `vercel.json` با `fluid: true` تنظیم کنید.
- [ ] متغیرهای محیطی (`DATABASE_URL`, `GOOGLE_API_KEY`) را در پنل تنظیم کنید.
- [ ] دیتابیس را از Marketplace (Neon/Prisma) متصل کنید.
- [ ] PPR را برای داشبورد فعال کنید.
- [ ] Feature Flags برای عرضه مرحله‌ای تعریف کنید.
- [ ] قوانین WAF + Bot Management را پیکربندی کنید.
- [ ] ریدایرکت/رایت‌های لازم (مثلاً به هاست RPA) را اضافه کنید.
- [ ] مانیتورینگ (Runtime Logs + Speed Insights) را فعال کنید.
- [ ] استقرار Preview را تست و سپس به Production ارتقا دهید.

---

> این راهنما مرجع زنده است؛ با تغییر مستندات Vercel به‌روزرسانی شود.
> نسخه‌ی قابل دسترسی برای ایجنت: `~/.hermes/skills/vercel-expert-reference/SKILL.md`
