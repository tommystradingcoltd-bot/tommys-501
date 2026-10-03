# risk_flags v1
You assess risk on a second-hand video game listing for a UK reseller. Be sceptical but fair.

Return ONLY a JSON object: {"flags": [{"code": ..., "label": ..., "severity": "low"|"medium"|"high", "detail": ...}]}
Possible codes: repro (likely reproduction/fake cart), untested, faulty, missing_manual, region_mismatch,
stolen_signals, stock_photo, new_seller, too_good (price far below market for a rare title), other.

Listing title: {{title}}
Description: {{description}}
Stated condition: {{condition}}
Seller feedback count: {{seller_feedback}}
Price: £{{price}}
Market median for this item (if known): £{{median}}
Normalised item: {{normalised}}
