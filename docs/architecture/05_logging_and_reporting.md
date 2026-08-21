> Legacy design note: current monitoring inventory is Prometheus, Alertmanager,
> Grafana, and node/Redis/Postgres/Nginx exporters. Runtime health still requires
> direct verification. See docs/BARPRO_KNOWLEDGE_GRAPH.md.

## ۵. سناریوهای مانیتورینگ و گزارش‌گیری (Logging & Reporting)

- یکپارچه‌سازی با **Prometheus + Grafana**: اکسپوز کردن متریک‌های موفقیت/شکست RPA، تاخیرهای حل کپچا، و درصد منابع درگیر.
- ثبت **اسکرین‌شات‌ها و سورس صفحات HTML** به صورت Base64 یا در ابجکت استور در هنگام بروز خطاهای "Selector Not Found" توسط کلاس `SmartLocator`.
- لاگ‌های اپلیکیشن (Application Logs) که توسط فریم‌ورک Logging در سطوح INFO/WARNING/ERROR مدیریت می‌شوند، مستقیماً می‌توانند به ELK Stack یا OpenSearch ارسال شوند.

---
