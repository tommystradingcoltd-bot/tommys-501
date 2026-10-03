# listing_copy v1
Write an eBay UK listing for a second-hand retro game item. Friendly, honest, UK English. Never call a reproduction
genuine. Describe faults plainly. Do not invent details that are not in the item data.

Return ONLY a JSON object:
- title: string, max 80 characters, SEO-friendly (platform, title, region, completeness, key selling points, no filler like "L@@K")
- condition_description: 2-4 sentences, honest, specific
- description: a short structured description with headings "What you get", "Condition", "Testing", "Postage"
- item_specifics: object of eBay item specifics (Platform, Game Name, Region Code, Genre, Publisher, Release Year, Features)

Item: {{item}}
Test results: {{tests}}
Niche: {{niche_name}}
