# Running RentFlow AI for the first time

Follow this in order. Each step assumes the previous one worked before
you move on — don't skip ahead if something errors.

## 0. What you need before starting

- **Node.js 18+** and **Python 3.11+** installed
- **MongoDB** — easiest options, pick one:
  - **Local install**: [MongoDB Community Server](https://www.mongodb.com/try/download/community) for your OS, then just run `mongod`
  - **Free hosted option**: [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register) free tier — no local install, you'll get a connection string like `mongodb+srv://...`
  - **Docker**, if you have it: `docker run -d -p 27017:27017 mongo`
- **An Anthropic API key** (console.anthropic.com) — only needed for AI Copilot / AI Actions / photo recognition. Everything else works without it.
- **SMTP credentials** — only needed for real email sending (renewal/reminder emails). A Gmail account with an [App Password](https://myaccount.google.com/apppasswords) works fine for testing. Everything else works without it.

## 1. Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Copy the environment template and fill it in:

```bash
cp .env.example .env
```

Open `.env` and set at minimum:
```
MONGO_URL=mongodb://localhost:27017        # or your Atlas connection string
JWT_SECRET=<any long random string>
```
Leave `ANTHROPIC_API_KEY` and the `SMTP_*` values blank for now — you can add them later once the basic app is working. Everything will run fine without them; only the AI and email features will return a clear "not configured" error until you add them.

## 2. Confirm MongoDB is reachable

```bash
python -c "
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
async def check():
    client = AsyncIOMotorClient('mongodb://localhost:27017')  # match your MONGO_URL
    print(await client.admin.command('ping'))
asyncio.run(check())
"
```
Expected output: `{'ok': 1.0}`. If this fails, fix your MongoDB connection before continuing — nothing past this point will work otherwise.

## 3. Seed the first accounts

```bash
python -m scripts.seed_users
```
Expected output:
```
Created staff account: staff@rentflow.demo / demo1234
Created tenant account: tenant@rentflow.demo / demo1234
Created vendor: Metro Plumbing (plumbing)
...
```
This is the **only** way to create the first staff account — by design, the API itself has no way to self-register as staff (see the README's security notes if you're curious why).

## 4. Start the backend

```bash
uvicorn main:app --reload --port 8000
```
Confirm it's actually up in a second terminal:
```bash
curl http://localhost:8000/api/health
# expect: {"status":"ok"}
```

## 5. Frontend setup

In a new terminal:
```bash
cd frontend
npm install
```
This was just verified to complete cleanly with zero errors before this bundle was handed to you.

## 6. Start the frontend

```bash
npm run dev
```
Vite will print a URL, almost always `http://localhost:5173`. The dev server is already configured (`vite.config.js`) to proxy `/api` requests to `http://localhost:8000`, so the backend from step 4 needs to still be running.

## 7. Open it in a real browser

Go to `http://localhost:5173`. You should see the RentFlow AI login screen.

Log in with:
- **Staff**: `staff@rentflow.demo` / `demo1234`
- **Tenant**: `tenant@rentflow.demo` / `demo1234`

This is the actual first moment this app has ever been seen in a real browser. Expect to find things — that's normal and expected for code that's only been tested programmatically until now.

## 8. What to do when something breaks

- **Blank white screen**: open your browser's dev console (F12) and read the actual error — it'll tell you far more than guessing.
- **"Failed to fetch" / network errors in the console**: almost always means the backend isn't running, isn't on port 8000, or the Vite proxy isn't matching — double check steps 4 and 6.
- **401 errors immediately after login**: check that `JWT_SECRET` in `.env` didn't change between when you logged in and now (changing it invalidates all existing tokens).
- **Empty dashboard / no data anywhere**: expected — the seed script only creates accounts and vendors, not properties/leases/tickets. Create a property via the UI, or `POST /api/properties` directly, to have something to look at.
- **AI features return "not configured"**: expected until you add `ANTHROPIC_API_KEY` to `.env` and restart the backend.

## 9. Once basic login and navigation work

Add real data to actually exercise the app:
1. Log in as staff, create a property with a few units (Dashboard won't show real numbers until this exists)
2. Create a lease for one unit, using the tenant account's email (`tenant@rentflow.demo`) as `residentEmail` — this is what lets that tenant account see unit-specific data
3. File a maintenance ticket, try assigning a vendor
4. Try an inspection, upload a photo
5. Add `ANTHROPIC_API_KEY` and restart the backend, then try AI Actions → "Generate new recommendations" and the AI Copilot

At this point you're genuinely using the app, not just running it — which is the actual goal.
