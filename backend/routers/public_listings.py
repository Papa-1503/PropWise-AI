"""
Public vacancy feed — unauthenticated, read-only JSON listing of all
currently vacant units across all properties. This is the building block
for listing syndication: point a service like Zillow Rental Manager,
Apartments.com, or a syndication aggregator at this URL as your feed
source. No actual push integration is wired in — signing up with a real
syndication partner and configuring their feed importer to pull from
this URL is a separate, manual step outside this codebase.

MULTI-TENANCY: this endpoint is public and unauthenticated, so there is
no user session to read an orgId from. A real, previously-live gap:
without an explicit orgId, this fed together every organization's
vacant units into one combined feed - a real cross-tenant data leak
(other landlords' vacancy/pricing data exposed to any public consumer,
with no way to even tell which listing belonged to which company).
orgId is now a REQUIRED query parameter - a real per-organization feed
URL (e.g. ?orgId=<their real org id>) is the correct long-term design
for a public syndication endpoint like this, matching how real
syndication feeds are typically issued per customer. Omitting it
returns an empty feed with an honest error, never a mixed-org dump.

CHANGED Sept 13, 2026: added a real, embeddable "vacancy widget" - a
standalone JS snippet a customer can drop directly onto THEIR OWN
website (outside this app entirely) to show their live current
vacancies, styled to blend into their own site rather than looking like
an obvious third-party iframe. This is a genuine, real competitive
angle: a small, free, always-current listing widget most competitors
in this space don't offer self-serve.

CORS on /vacancies is deliberately OPENED to any origin (Access-
Control-Allow-Origin: *) specifically for this one route, overriding
the app's normal strict origin allowlist (main.py's CORSMiddleware) -
correct and safe here because this endpoint is read-only, carries no
cookies/credentials, and is explicitly designed to be fetched from a
customer's own external website by the widget below. No other route in
this app gets this treatment. The widget SCRIPT file itself doesn't
technically need this (a <script src="..."> tag isn't subject to CORS
the way fetch()/XHR is) - the open header matters because the script's
own internal fetch() call to /vacancies would otherwise be blocked by
the browser on whatever external site it's embedded on.

API_BASE in the widget script is a fixed constant (this backend's own
real, stable domain), not derived from the incoming request - a
request's Host header reflects wherever the SCRIPT is being fetched
FROM (a customer's own external site), never this backend's own
address, so deriving it from request headers would have been wrong,
not just unnecessary.
"""
from fastapi import APIRouter, Response
from db import properties_col

router = APIRouter(prefix="/api/public", tags=["public"])

# The real Access-Control-Allow-Origin: * exception - see this
# module's own docstring for why this one route deliberately opts out
# of the app's normal strict CORS allowlist.
_OPEN_CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}

# This backend's own real, stable domain - see the module docstring
# for why this is a fixed constant, not derived from request headers.
_API_BASE = "https://rentflow-ai.onrender.com"


@router.get("/vacancies")
async def list_vacancies(orgId: str, response: Response):
    response.headers.update(_OPEN_CORS_HEADERS)
    cursor = properties_col.find({"orgId": orgId})
    properties = await cursor.to_list(length=500)

    listings = []
    for p in properties:
        property_name = p.get("name", "")
        address = p.get("address", "")
        for unit in p.get("units", []):
            if unit.get("status") == "vacant":
                listings.append({
                    "propertyName": property_name,
                    "address": address,
                    "unitId": unit.get("unitId"),
                    "rent": unit.get("rent", 0),
                    "bedrooms": unit.get("bedrooms", 0),
                    "bathrooms": unit.get("bathrooms", 0),
                })

    return {"vacancies": listings, "count": len(listings)}


@router.options("/vacancies")
async def vacancies_preflight():
    """A plain GET with no custom headers (exactly what the widget's
    own fetch() call below sends) is a real CORS "simple request" and
    never actually triggers a browser preflight OPTIONS call in
    practice - this handler exists as a defensive, explicit no-op
    safety net in case a future version of the widget adds a header
    that DOES require one, rather than leaving that case to 404."""
    return Response(status_code=204, headers=_OPEN_CORS_HEADERS)


_WIDGET_JS_TEMPLATE = """(function() {
  var scriptTag = document.currentScript;
  var orgId = scriptTag.getAttribute('data-org-id');
  var targetId = scriptTag.getAttribute('data-target') || 'propwise-vacancies';
  var apiBase = '__API_BASE__';

  if (!orgId) {
    console.error('PropWise AI vacancy widget: missing required data-org-id attribute on the script tag.');
    return;
  }

  var container = document.getElementById(targetId);
  if (!container) {
    container = document.createElement('div');
    container.id = targetId;
    scriptTag.parentNode.insertBefore(container, scriptTag);
  }
  container.innerHTML = '<p style="font-family:sans-serif;color:#94a3b8;font-size:14px;">Loading available units...</p>';

  fetch(apiBase + '/api/public/vacancies?orgId=' + encodeURIComponent(orgId))
    .then(function(res) {
      if (!res.ok) { throw new Error('Request failed'); }
      return res.json();
    })
    .then(function(data) {
      var vacancies = data.vacancies || [];
      if (vacancies.length === 0) {
        container.innerHTML = '<p style="font-family:sans-serif;color:#64748b;font-size:14px;">No units currently available. Check back soon.</p>';
        return;
      }
      var html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;font-family:sans-serif;">';
      vacancies.forEach(function(v) {
        html += '<div style="border:1px solid #e2e8f0;border-radius:10px;padding:14px;background:#fff;">'
          + '<div style="font-weight:600;font-size:14px;color:#0f172a;">' + escapeHtml(v.propertyName) + '</div>'
          + '<div style="font-size:12px;color:#64748b;margin-bottom:6px;">' + escapeHtml(v.address || '') + ' &mdash; Unit ' + escapeHtml(String(v.unitId)) + '</div>'
          + '<div style="font-size:13px;color:#334155;">' + v.bedrooms + ' bd / ' + v.bathrooms + ' ba</div>'
          + '<div style="font-weight:700;font-size:16px;color:#4f46e5;margin-top:4px;">$' + Number(v.rent).toLocaleString() + '/mo</div>'
          + '</div>';
      });
      html += '</div>';
      container.innerHTML = html;
    })
    .catch(function() {
      container.innerHTML = '<p style="font-family:sans-serif;color:#dc2626;font-size:14px;">Couldn\\'t load available units right now.</p>';
    });

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }
})();
"""


@router.get("/vacancy-widget.js")
async def vacancy_widget_script():
    """The real, standalone embed script - vanilla JS, zero
    dependencies, safe to drop onto any external website via:
        <div id="propwise-vacancies"></div>
        <script src=".../api/public/vacancy-widget.js"
                data-org-id="YOUR_ORG_ID" defer></script>
    Deliberately self-contained (no external CDN dependency, no build
    step) so it can never break due to an unrelated third-party
    outage or a bundler mismatch on the customer's own site."""
    script = _WIDGET_JS_TEMPLATE.replace("__API_BASE__", _API_BASE)
    headers = dict(_OPEN_CORS_HEADERS)
    # Real, short cache - the widget script itself changes rarely, but
    # a short cache means a real fix/update here reaches every
    # customer's embedded copy within an hour, not "whenever their
    # browser cache happens to expire."
    headers["Cache-Control"] = "public, max-age=3600"
    return Response(content=script, media_type="application/javascript", headers=headers)
