// Real, deliberate: this URL stays "rentflow-ai" even though the
// product itself was renamed to PropWise AI. Render's .onrender.com
// subdomain is permanently locked to a service once created and
// cannot be changed - confirmed directly via Render's own dashboard
// and a years-old open feature request on their own feedback board.
// The service's display Name was renamed to "propwise-ai-backend"
// (cosmetic, internal-only), but the live URL can't follow. A real
// custom domain (e.g. propwiseai.com) is the actual supported path
// to a branded URL, deliberately not pursued for now - decided to
// live with the old URL rather than take on that cost/DNS work.
export const API_BASE = "https://rentflow-ai.onrender.com/api";
