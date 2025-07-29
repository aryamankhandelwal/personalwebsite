# Blog Post Changes Log

## Methodology
- Track major changes that are "final" (user confirmed)
- Include context about the methodology to help replicate across all posts
- Focus on styling consistency and navigation improvements

## Major Changes Made

### 1. Font Consistency and Navigation (blog12.html - FINAL)
**Date:** [Current Date]

**Changes Made:**
1. **Font Consistency:**
   - Added Google Fonts (IBM Plex Mono) to match index.html and blog.html
   - Removed custom inline styles that override global link colors
   - Applied consistent font sizing (0.85rem for titles and content)

2. **Navigation:**
   - Added "< Back" link above title that redirects to blog.html
   - "<" is plain white text (no underline/hover)
   - "Back" is underlined link with white default, blue hover (#8bb3ff)

3. **Content Cleanup:**
   - Removed emoji above title (🇮🇳)
   - Ensured consistent spacing and indentation
   - Simplified HTML structure (removed unnecessary end section)

**CSS Rules Added:**
```css
.back-link {
    color: #fff !important;
    text-decoration: underline;
    font-size: 0.85rem;
}
.back-link:hover {
    color: #8bb3ff !important;
}
```

**Methodology for Replication:**
- Always add Google Fonts links in head section
- Remove any custom inline styles that override global colors
- Add back navigation with proper styling
- Ensure font-size: 0.85rem for consistency
- Remove decorative emojis from titles
- Maintain proper HTML structure with nav, section, main-container
- Use relative paths for navigation (../blog.html, ../index.html)

**Files to Update:** All blog*.html files in blogs/ directory

### 2. Padding and Title Formatting (blog12.html - FINAL)
**Date:** [Current Date]

**Changes Made:**
1. **Padding Consistency:**
   - Added `margin-top:2rem` to blog-within div to match spacing between "Aryaman Khandelwal" and "< Back" link
   - Ensures consistent spacing across blog.html and individual blog posts

2. **Title Formatting:**
   - Added square brackets around blog post titles: "[On the current state of India…]"
   - Reduced spacing between title and date by changing `margin-bottom` from `1.5rem` to `0.5em`
   - Creates consistent title format with other sections on the website

**Methodology for Replication:**
- Apply `margin-top:2rem` to main content div for consistent top spacing
- Wrap blog post titles in square brackets: "[Title]"
- Use `margin-bottom:0.5em` for tight spacing between title and date
- Maintain consistent font-size: 0.85rem for all text elements

**Files to Update:** All blog*.html files in blogs/ directory

### 3. Hyperlink Styling Rules (ALL BLOG POSTS - FINAL)
**Date:** [Current Date]

**Rules for Hyperlinks in Blog Posts:**
1. **Default Styling:**
   - White text color (`color: #fff`)
   - Underlined (`text-decoration: underline`)

2. **Hover Effect:**
   - Turn blue on hover (`color: #8bb3ff`)

3. **Target Behavior:**
   - External links: Open in new tab (`target="_blank"`)
   - Internal links (own site): Open in same tab (no target attribute)

**CSS Rules to Add:**
```css
.blog-within a {
    color: #fff !important;
    text-decoration: underline;
}
.blog-within a:hover {
    color: #8bb3ff !important;
}
```

**Methodology for Replication:**
- Add CSS rules to override global link colors for blog content
- Ensure all external links have `target="_blank"`
- Internal navigation links (Back, index.html, blog.html) stay in same tab
- Maintain consistent hover effects across all blog posts

**Files to Update:** All blog*.html files in blogs/ directory

### 4. Horizontal Line Styling (blog1.html - FINAL)
**Date:** [Current Date]

**Changes Made:**
1. **Line Thickness:**
   - Changed from default `<hr>` to custom styling: `<hr style="border: none; height: 1px; background-color: #fff; margin: 0.5rem 0;">`
   - Creates much thinner 1px line instead of default thicker line

2. **Consistent Spacing:**
   - Added single `<br>` before horizontal line
   - Set `margin: 0.5rem 0` for equal spacing above and below line
   - Added single `<br>` after horizontal line
   - Ensures text above and below line have equal spacing relative to line

3. **Font Size Consistency:**
   - Wrapped P.S. text in `<span style="font-size:0.85rem;">` to match text above line

**Methodology for Replication:**
- Replace all `<hr>` elements with custom styling for consistent thin lines
- Use `margin: 0.5rem 0` for balanced spacing
- Add single line breaks before and after horizontal lines
- Ensure text below horizontal lines has same font size as text above
- Apply to any blog posts with horizontal dividers

**Files to Update:** All blog*.html files in blogs/ directory that contain horizontal lines

### 5. Image Path and Spacing Fixes (blog1.html - FINAL)
**Date:** [Current Date]

**Changes Made:**
1. **Correct Image Paths:**
   - Changed from `images/filename.jpg` to `../images/filename.jpg`
   - Blog files are in `blogs/` subdirectory, so need `../` to access parent `images/` directory

2. **Consistent Image Spacing:**
   - Ensure equal spacing before and after images
   - Use consistent `<br><br>` tags around images for uniform spacing

**Methodology for Replication:**
- All image paths in blog posts should use `../images/` prefix
- Check for any images using `images/` path and update to `../images/`
- Ensure consistent spacing around images with equal line breaks before and after (`<br><br>` before and `<br><br>` after)
- Apply to any blog posts containing images

**Files to Update:** All blog*.html files in blogs/ directory that contain images

### 6. Blog Content Indentation and Spacing (blog1.html - FINAL)
**Date:** [Current Date]

**Changes Made:**
1. **Content Indentation:**
   - Wrapped blog content after date in `<div style="margin-left:1.5em;font-size:0.85rem;">`
   - Matches indentation used in index.html for "About" and "I'm currently..." sections
   - Creates consistent visual hierarchy across all blog posts

2. **Date Spacing:**
   - Reduced spacing between date and first line from `<br><br>` to `<br>`
   - Eliminates excessive white space between date and content

3. **Horizontal Line Spacing:**
   - Added `<br><br>` before horizontal line to match `<br>` after it
   - Ensures equal spacing around horizontal dividers
   - Creates balanced visual spacing for text above and below lines

**Methodology for Replication:**
- Wrap all blog content after the date in indented div with `margin-left:1.5em`
- Use single `<br>` after date to reduce excessive spacing
- Add `<br><br>` before horizontal lines to match spacing after them
- Maintain consistent font-size: 0.85rem within indented content
- Apply to all blog posts for uniform content indentation

**Files to Update:** All blog*.html files in blogs/ directory 