# Project Roadmap: nugme.org Storefront

## 1. Overview
- **Brand**: NugMe (`nugme.org`)
- **Theme**: Shopify Dawn (forked at `Michael-Scrumlord/dawn`)
- **Mascot**: Animated/illustrated running nugget (`assets/nug-mascot.png` & `assets/nugget-anime.jpeg`)
- **Dev Store**: `nugme-dev-i61jtgyy.myshopify.com`
- **Offerings**: Multi-disciplinary studio offering physical handcrafted maker goods (bookbindings, sewing, canvas bags, woodburnings, lace) alongside digital products (software subscriptions, audio tools, digital music).

---

## 2. Design System & Brand Tokens

| Token | Hex | Role | Usage |
| :--- | :--- | :--- | :--- |
| **Primary** | `#E4A13A` | Crispy Golden Crust | Primary buttons, active highlights, key accents |
| **Accent / Sauce** | `#F7D570` | Honey Mustard | Secondary badges, callout cards, promo banners |
| **Text / Deep Crunch** | `#3E2614` | Dark Fry Brown | Body text, headings, high-contrast outlines |
| **Background / Buttermilk** | `#FFFDF7` | Warm Off-White | Primary store canvas (replaces cold #FFFFFF) |
| **Card / Surface** | `#FFF6DE` | Soft Golden Dip | Product card backgrounds, drawer menus |
| **Crispy Dark** | `#2A180B` | Deep Crust Dark | Dark mode sections, footer background |

### Geometry & Shape Language
- **Button Radius**: Rounded pill (`24px` to `40px` or `9999px`)
- **Card Corner Radius**: `16px` to `20px`
- **Badge Radius**: `40px` (pill)
- **Typography Direction**: Friendly, bold, rounded display headers (e.g., Fredoka, Baloo 2, or Outfit) with clean sans-serif body.

---

## 3. Current Progress
- [x] Cloned `Michael-Scrumlord/dawn` into local repository.
- [x] Connected Shopify CLI to `nugme-dev-i61jtgyy.myshopify.com`.
- [x] Copied character mascot image to `assets/nug-mascot.png` and synced to remote theme.
- [x] Verified local server preview at `http://127.0.0.1:9292`.

---

## 4. Pending Implementation Tasks

### Phase 1: Brand Styling & Theme Settings
- [x] Configure `config/settings_data.json`:
  - Updated `color_schemes` (scheme-1 through scheme-5) with nugget brand hex values.
  - Set button border radius (40px pill), card border radius (16px), and shadow properties.
- [x] Update `assets/base.css` with NugMe brand variables, button hover lift/glow, card elevation, and mascot animation utilities.

### Phase 2: Header & Mascot Logo Lockup
- [x] Update header section (`sections/header.liquid`) with `nug-mascot.png` and custom `NugMe.org` lockup.
- [x] Set up playful announcement bar text and scheme-5 styling in `sections/header-group.json`.

### Phase 3: Custom Hero Section
- [x] Create dedicated hero section (`sections/nug-hero.liquid`) featuring:
  - Animated mascot showcase with glowing backdrop and floating tags ("100% Golden Crunch", "Secret Recipe").
  - Catchy hero headline with golden highlight and dual CTAs ("Shop The Drop" / "Explore Sauces").
  - Trust indicators strip (Always Crispy, Extra Sauce Guaranteed, Fast Global Shipping).
- [x] Integrate hero section into `templates/index.json`.

### Phase 4: Product Grid & Card Refinements
- [x] Configured product cards in `config/settings_data.json`:
  - Soft rounded card corners (16px) and warm card surface scheme.
  - Honey mustard (`#F7D570`) sale badge and crisp dark (`#2A180B`) sold-out badge.
  - Enabled standard quick-add buttons and mobile swipe grid in `templates/index.json`.

### Phase 5: Footer & Community Links
- [x] Style footer (`sections/footer.liquid` & `sections/footer-group.json`):
  - Applied Crispy Dark (`#2A180B`) color scheme.
  - Added mascot branding fallback and "The Nug Manifesto" about block.
  - Configured high-conversion newsletter CTA ("Join The Crispy Crew • Get 10% Off").

### Phase 6: Production Launch Handoff
- [ ] Review live store on local dev (`http://127.0.0.1:9292`) or cloud preview.
- [ ] Import `docs/nugme-products-import.csv` into Shopify Admin to populate all catalog items.
- [ ] Push local commits to `origin/main` (`Michael-Scrumlord/dawn`).
- [ ] Connect custom domain `nugme.org` in Shopify Admin (*Settings > Domains*).

---

## 5. Catalog Breakdown (Physical & Digital)

| Category | Type | Products | Shipping |
| :--- | :--- | :--- | :--- |
| **Software** | Digital Subscription | *NugMe Studio Pro Subscription* (Monthly & Annual) | No (`FALSE`) |
| **Software** | Digital Audio Tool | *Gourmet Heat Attack* Analog Saturation & Resonant Filter (VST3/AU) | No (`FALSE`) |
| **Music** | Digital Album | *Dipping Sauce Aura* Original Soundtrack (Lossless FLAC/MP3) | No (`FALSE`) |
| **Music** | Sample Pack | *Crispy Crunch* Drum & Foley Production Sample Pack Vol. 1 | No (`FALSE`) |
| **Bookbinding** | Physical Craft | *Hand-Bound Full Leather Grimoire* & *Coptic Exposed-Spine Sketchbook* | Yes (`TRUE`) |
| **Sewing & Bags**| Physical Craft | *Heavyweight 18oz Duck Canvas Tote* & *Waxed Canvas Tool Roll* | Yes (`TRUE`) |
| **Woodburning** | Physical Craft | *'Gourmet Heat Attack' Cedar Round* & *Botanical Oak Coaster Set* | Yes (`TRUE`) |
| **Lace & Textiles**| Physical Craft | *Artisan Bobbin Lace Heirloom Collar* & *Hand-Tatted Lace Bookmark* | Yes (`TRUE`) |

### How to Import Products to Shopify Admin
1. Open [Shopify Admin Products](https://nugme-dev-i61jtgyy.myshopify.com/admin/products).
2. Click **Import** (top right).
3. Select `dawn/docs/nugme-products-import.csv`.
4. Click **Upload and continue** -> **Import products**.
5. All 12 products, 19 variants, prices, digital/physical flags, and tags are populated instantly.

---

## 6. Development Reference

```bash
# Start local theme dev server with live reload
cd dawn
shopify theme dev --store nugme-dev-i61jtgyy.myshopify.com --store-password tubowp

# Commit and push changes
git add .
git commit -m "feat: brand styling updates"
git push origin main
```
