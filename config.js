/* =====================================================================
   COMPETITOR CONTENT TRACKER — SETTINGS FILE
   ---------------------------------------------------------------------
   This is the ONE file to edit when something changes:
   - add or remove a company
   - rename, add or remove a category (list is still a DRAFT)
   - change the status thresholds (e.g. 3x for "Big gap")
   Keep the quotes and commas exactly as they are when editing.
   ===================================================================== */

window.TRACKER_CONFIG = {

  // The company everyone is compared against.
  baseline: "Zoho CRM",

  // Companies shown on the dashboard, in column order.
  // role: "baseline" or "competitor". color: used in charts and badges.
  // feeds:        RSS feeds that are always read.
  // backupFeeds:  read only if every feed above returns nothing (Bing / Google News, as in the Deluge bot).
  // No small-business filter: every new page counts.
  companies: [
    { name: "HubSpot", role: "competitor", color: "#ff7a59",
      feeds: [ "https://blog.hubspot.com/marketing/rss.xml",
               "https://blog.hubspot.com/sales/rss.xml",
               "https://blog.hubspot.com/service/rss.xml" ],
      backupFeeds: [ "https://www.bing.com/news/search?q=site%3Ablog.hubspot.com&format=RSS",
                     "https://news.google.com/rss/search?q=site:blog.hubspot.com" ] },
    { name: "monday.com", role: "competitor", color: "#6161ff",
      feeds: [],
      sitemaps: [ { url: "https://monday.com/blog/sitemap_index.xml",
                    include: ["monday\\.com/blog/"], exclude: ["/blog/(category|tag|author|page)/"] } ],
      backupFeeds: [ "https://news.google.com/rss/search?q=site:monday.com/blog&hl=en-US&gl=US&ceid=US:en" ] },
    { name: "Pipedrive", role: "competitor", color: "#1a9e5c",
      feeds: [],
      sitemaps: [ { url: "https://www.pipedrive.com/sitemaps/en-blog-pages.xml", include: ["/en/blog/"] } ],
      backupFeeds: [ "https://news.google.com/rss/search?q=site:pipedrive.com/en/blog&hl=en-US&gl=US&ceid=US:en" ] },
    { name: "Salesforce", role: "competitor", color: "#0b76d1",
      feeds: [ "https://www.salesforce.com/blog/feed/",
               "https://news.google.com/rss/search?q=site:salesforce.com/blog+when:7d&hl=en-US&gl=US&ceid=US:en" ],
      backupFeeds: [ "https://news.google.com/rss/search?q=site:salesforce.com/blog+when:7d",
                     "https://www.bing.com/news/search?q=site%3Asalesforce.com%2Fblog&format=RSS" ] },
    { name: "Brevo", role: "competitor", color: "#0b996e",
      feeds: [],
      sitemaps: [ { url: "https://www.brevo.com/sitemap_en.xml",
                    include: ["^https://www\\.brevo\\.com/blog/"], exclude: ["/blog/(category|tag|author|page)/"] } ],
      backupFeeds: [ "https://news.google.com/rss/search?q=site:brevo.com/blog&hl=en-US&gl=US&ceid=US:en" ] },
    { name: "The Hustle", role: "competitor", color: "#b8860b",
      feeds: [ "https://thehustle.co/news/rss.xml" ],
      backupFeeds: [ "https://www.bing.com/news/search?q=site%3Athehustle.co&format=RSS",
                     "https://news.google.com/rss/search?q=site:thehustle.co" ] },
    { name: "Zoho CRM", role: "baseline", color: "#e42527",
      feeds: [ "https://www.zoho.com/blog/crm/feed" ],
      // English zoho.com/crm/ pages only; product help, developer docs, pricing and feature pages are left out
      sitemaps: [ { url: "https://www.zoho.com/crm/sitemap.xml",
                    include: ["^https://www\\.zoho\\.com/crm/"],
                    exclude: ["/crm/(help|developer|kb|webinars?|events?|signup|pricing|compare|features|editions|demo|partners?|marketplace|mobile|security|terms|privacy|gdpr)", "/crm/.*(pricing|signup|login)"] } ],
      backupFeeds: [ "https://news.google.com/rss/search?q=site:zoho.com/blog/crm" ] }
  ],

  // DRAFT category list — awaiting manager approval.
  // "Other" should always stay last.
  categories: [
    { name: "AI in sales",                    covers: "AI agents, AI assistants, AI for selling and forecasting" },
    { name: "Lead management",                covers: "Lead generation, capture, scoring, nurturing" },
    { name: "Pipeline and deals",             covers: "Pipeline stages, deal tracking, closing, forecasting" },
    { name: "Sales process and productivity", covers: "Sales methods, tips, team management, coaching" },
    { name: "Sales templates and resources",  covers: "Templates, scripts, checklists, free downloads" },
    { name: "Marketing and email",            covers: "Email campaigns, marketing automation, social" },
    { name: "Customer service and retention", covers: "Support, customer success, loyalty, churn" },
    { name: "CRM basics and comparisons",     covers: "What is a CRM, choosing a CRM, X vs Y, alternatives" },
    { name: "Small business growth",          covers: "Running and growing a small business, general SMB advice" },
    { name: "Automation and integrations",    covers: "Workflows, integrations, apps, no-code tools" },
    { name: "Customer stories",               covers: "Case studies, testimonials" },
    { name: "Other",                          covers: "Anything that fits none of the above" }
  ],

  // Sitemap pages count only if the page's own publish date is within this many days
  // (or, with no publish date, from the day the tracker first sees a brand-new address).
  sitemapLookbackDays: 45,

  // Calls to action: what a page asks the reader to do.
  // "words" are what the collector looks for in buttons and links on each page (used from Phase 2).
  ctaTypes: [
    { name: "Free trial / sign up",  words: ["free trial", "start free", "get started free", "sign up free", "try free"] },
    { name: "Book a demo",           words: ["book a demo", "request a demo", "get a demo", "schedule a demo"] },
    { name: "Template / download",   words: ["download", "free template", "get the template", "free kit", "ebook"] },
    { name: "Free tool",             words: ["free tool", "calculator", "generator", "grader"] },
    { name: "Webinar / event",       words: ["webinar", "register now", "watch on demand", "event"] },
    { name: "Newsletter",            words: ["subscribe", "newsletter"] },
    { name: "Talk to sales",         words: ["contact sales", "talk to sales", "see pricing", "get a quote"] }
  ],

  // Public site (GitHub Pages). The "Watch this page" field opens a pre-filled issue in this repo;
  // GitHub Actions then adds and checks the page (only issues opened by the repo owner are accepted).
  githubRepo: "Sadhana73/competitor-content-tracker",

  // Status rules for the home screen.
  thresholds: {
    bigGapMultiple: 3   // "Big gap" when the top competitor published this many times Zoho CRM or more
  },

  // All dates are stored and shown in this time zone.
  timeZone: "Asia/Kolkata"
};
