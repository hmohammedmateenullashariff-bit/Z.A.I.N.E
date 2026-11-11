---
name: website-designing
description: Modern responsive website design, design systems, UI/UX architecture, Tailwind CSS, typography hierarchies, micro-interactions, dark mode styling, and Core Web Vitals optimization. Use when designing, styling, prototyping, or reviewing web applications and landing pages.
---

# Modern Website Designing & UI/UX Architecture

Specialized design engineering capability for architecting responsive, aesthetic, high-converting, and accessible web experiences.

## Core Capabilities

1. **Design System & Visual Aesthetics**:
   - Palette Architecture: 60-30-10 color harmony (60% background/neutral, 30% surface/structure, 10% bold accent).
   - Glassmorphism & Depth: layered backdrop-filter blurs (`backdrop-blur-md`), subtle translucent borders (`border-white/10`), ambient radial glow gradients.
   - Typography Hierarchies: modern monospace and sans-serif pairings (Geist, Inter, Fira Code, Outfit) with strict line-height and letter-spacing scales.

2. **Responsive Layouts & Component Patterns**:
   - Mobile-first CSS Grid and Flexbox layouts.
   - Fluid typography using `clamp(1rem, 2.5vw, 2.5rem)` to avoid jarring breakpoint snaps.
   - Sticky navigation bars, responsive hero banners, card grids with hover elevation, and interactive tabs.

3. **Micro-Interactions & State Styling**:
   - Smooth 150ms–300ms cubic-bezier transition curves on hover, focus-visible, and active states.
   - Accessible keyboard navigation indicators and high-contrast focus rings.
   - Reduced motion queries (`@media (prefers-reduced-motion: reduce)`).

4. **Performance & Core Web Vitals**:
   - Zero layout shift (CLS < 0.1) by reserving image aspect ratios and skeleton loading frames.
   - Sub-second Largest Contentful Paint (LCP < 1.2s) through critical CSS inlining and modern WebP/SVG asset formats.

