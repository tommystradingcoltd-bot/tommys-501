# normalise v1
You are an expert in second-hand video games and consoles sold in the UK. Turn one marketplace listing into structured data.

Niche: {{niche_name}}
Known platforms (use these exact names where they fit): {{platforms}}

Niche hints:
{{hints}}

Return ONLY a JSON object with these keys:
- platform: string (one of the known platforms, or your best name, or "unknown")
- title: string (the canonical game/console name, e.g. "Super Mario World", or "console" for a console)
- category: "game" | "console" | "accessory" | "bundle"
- region: "PAL" | "NTSC-U" | "NTSC-J" | "unknown"
- completeness: "loose" | "boxed" | "cib" | "sealed" | "graded" | "unknown"
- condition_notes: short string summarising stated condition and faults
- is_bundle: boolean
- bundle_items: list of {platform, title, completeness} for each identifiable item in a bundle (empty if not a bundle)
- console_model: string (model/colour, e.g. "SNES SNSP-001 PAL", "N64 Jungle Green", "" if n/a)
- accessories: list of strings (controllers, leads, memory cards)
- confidence: number 0-1 for how sure you are about platform/title/completeness

Listing title: {{title}}
Listing description: {{description}}
Stated condition: {{condition}}
Price: £{{price}}
