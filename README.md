# GeneMeal

GeneMeal is a local educational notebook. You download your own 23andMe raw-data zip, the app checks that it looks like genotype text, `snps` counts markers, and a short map of publicly discussed nutrition SNPs drafts a 7-day menu. Two toggles, **weight loss** and **build muscle**, change generic calorie and protein placeholders.

**This is not medical advice.** It does not diagnose, treat, or prevent any condition. Effect sizes for common markers are usually small. Talk with a clinician or registered dietitian before changing how you eat.

**Have a lawyer review privacy terms, consent, and genetic-data handling before any public launch.** Do not deploy this scaffold as a production service.

There is no 23andMe API for third parties. The app only links to [https://you.23andme.com/tools/data/](https://you.23andme.com/tools/data/) so you can request the file yourself.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export SECRET_KEY=dev-only-change-me
export GENEMEAL_FERNET_KEY="$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")"
# optional — without it, menus use an approximate offline food table
export FDC_API_KEY=""
export PORT=8741

python app.py
```

Open http://127.0.0.1:8741/

Tests:

```bash
pytest -q
```

The test suite mocks FoodData Central and refuses live HTTP (`GENEMEAL_FORBID_NETWORK=1`). It does not call USDA or 23andMe.

## What the three steps do

1. A button opens the 23andMe raw-data page in a new tab.
2. The page explains the date-of-birth confirm, the checkbox, and the submit, then the wait for the “raw data download is ready” email (often about a week, sometimes up to 30 days). “I requested my file” stores reminder times about 7 days and about 30 days out. “I'm waiting for the email” sets status `waiting_email`.
3. Drag-and-drop (or browse) uploads the `genome_….zip`. The server unzips it, rejects PDFs, images, and files without a `#` header plus `rsid`, `chromosome`, `position`, and `genotype` columns, and caps uploads at 50 MB.

After a successful read you get a marker count, genome build, and the starter trait labels. **Confirm** keeps the trait summary and deletes the encrypted raw zip. The week screen has the two toggles, **Generate**, a 7-day view, and the not-medical-advice disclaimer.

Statuses: `new`, `requested`, `waiting_email`, `uploaded`, `parsed`, `failed`.

A rejected upload on a session that already has notes does not wipe those notes. A rejected upload before that sets `failed`.

## Encryption and delete

Uploaded bytes are encrypted with Fernet before they touch `DATA_DIR`. The full raw table is not stored in plaintext. After you confirm, the encrypted zip is deleted and the encrypted trait summary (and any generated menu) remain until you delete them.

`DELETE /account/data` (and the checkbox form that POSTs to the same path) removes that session’s files and database rows.

Generate a key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

If `GENEMEAL_FERNET_KEY` is unset, a dev key is written to `DATA_DIR/.fernet_key`. Do not use that fallback on a shared host. Losing the key makes existing ciphertext unreadable.

Original zip filenames are not stored. 23andMe’s names often include the customer’s name.

## Environment

| Variable | Role |
| --- | --- |
| `SECRET_KEY` | Signs the session cookie. Set this in any shared environment. |
| `GENEMEAL_FERNET_KEY` | Fernet key for files and saved notes. See the generator above. |
| `FDC_API_KEY` | USDA FoodData Central key. Empty means the offline approximate table. Never hard-code a key. |
| `DATA_DIR` | Where the SQLite file, encrypted uploads, and FDC cache live. Default `./data`. |
| `GEO_BLOCK_ENABLED` | `1` turns on the 19-state genetic-privacy block (HTTP 451). Default off. |
| `REMINDER_EMAIL_ENABLED` | `1` logs a stub “send” for due reminders. This build does not open SMTP and does not deliver mail. Default is log-only, and the address is not written to the log. |
| `PORT` | Listen port for `python app.py`. Default `8741`. |
| `GENEMEAL_COOKIE_SECURE` | `1` marks the session cookie Secure. Leave unset for local HTTP. |
| `GENEMEAL_FORBID_NETWORK` | `1` makes the FDC client refuse live HTTP. The test suite sets this. |

Reminders that are due can be recorded with `POST /account/reminders/process` (CSRF token required). Nothing sends email.

Geo-block denies log the state code and path only. Raw IPs are not logged.

## FoodData Central

`fdc.py` calls `https://api.nal.usda.gov/fdc/v1` for search and food detail, caches responses in memory and in `DATA_DIR/fdc_cache.json`, and waits about 0.35 seconds between live calls. Nutrient energy is kcal (id 1008) and protein is id 1003.

Get a key from the USDA FoodData Central API docs when you want live foods. Until then, menus are labeled approximate.

## Trait map

`traits.py` is a starter set of 11 markers (MTHFR, FTO, APOA2, TCF7L2, MCM6/LCT, FADS1, CYP1A2, GC, BCMO1). Confidence is only low or medium. Genotypes are the plus-strand letters in a 23andMe file, which do not always match the letters in older papers. The notes in that file say what is and is not being claimed. Extend the list only with markers you can cite, and keep the medical disclaimer.

## Tests

```bash
pytest -q
```

Covered: the existing geo-block tests, upload acceptance and rejection (synthetic genome zip, PDF, image, non-genome text, size), trait mapping, meal-plan shape and toggles, mocked FDC (no live network), encrypted storage, delete-my-data, and status transitions.

## Next steps before any launch

Do not deploy this tree as-is.

1. Lawyer review of the privacy policy, terms, consent, retention, and the state genetic-privacy list in `blocked_states.py`.
2. Create a USDA FoodData Central key and set `FDC_API_KEY` in the host environment. Do not commit it.
3. Set `SECRET_KEY` and `GENEMEAL_FERNET_KEY` in the host environment. Keep the Fernet key. There is no recovery if it is lost.
4. Turn on `GEO_BLOCK_ENABLED=1` only after that review. Unknown IP lookups stay allowed; robots and the favicon stay reachable.
5. Render (or any other host) is a later decision. A `Procfile` is present (`gunicorn app:app`) so a host can boot the app, but this project does not deploy itself. Wire reminders to a real mailer only after the legal review — the current sender is a stub.
6. Replace the anonymous session cookie with a real account design if more than one person will use a server. The session id is a convenience for a local demo, not production authentication.
