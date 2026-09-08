/**
 * legalContent.js
 *
 * Structured content for the public /terms and /privacy pages,
 * rendered by LegalDocument.jsx. This is the SAME real substance as
 * the standalone Word documents (PropWise_AI_Terms_of_Service_DRAFT.docx
 * and PropWise_AI_Privacy_Policy_DRAFT.docx) condensed to plain HTML-
 * friendly paragraphs rather than duplicated as a separate, drifting
 * draft - if you revise the Word documents after attorney review,
 * bring those same changes back here too, or this in-app version will
 * silently fall out of sync with what you actually publish elsewhere.
 *
 * DRAFT STATUS: this text has NOT been reviewed by an attorney (see
 * LegalDocument.jsx's own banner, which is the real, load-bearing
 * warning - not just decoration). Do not remove the draft banner
 * until real counsel has signed off on the content below.
 */

export const SUBPROCESSORS = [
  { name: "Stripe, Inc.", purpose: "Payment processing (subscription billing and resident rent/ACH payments)", data: "Payment method tokens, transaction records, billing contact info" },
  { name: "Twilio Inc.", purpose: "SMS and voice calling (resident/tenant communications, after-hours maintenance routing)", data: "Phone numbers, message/call content and metadata" },
  { name: "Anthropic, PBC", purpose: "AI-powered features (assistants, document extraction, automated recommendations)", data: "Relevant portfolio/lease/maintenance context provided to the feature at the time of use" },
  { name: "Cloudinary Ltd.", purpose: "File and photo storage (inspection photos, lease documents, uploaded screening documents)", data: "Uploaded images and documents" },
  { name: "MongoDB, Inc. (Atlas)", purpose: "Primary application database hosting", data: "All Customer Data stored by the Service" },
  { name: "Render Services, Inc.", purpose: "Application hosting infrastructure", data: "All data in transit through the hosted application" },
  { name: "Intuit Inc. (QuickBooks Online)", purpose: "Optional accounting sync, only if you connect it", data: "Payment and customer records you choose to sync" },
  { name: "Seam Labs, Inc.", purpose: "Optional smart-lock integration, only if you connect it", data: "Access codes and lock-event logs for connected units" },
];

export const TERMS_OF_SERVICE = {
  title: "Terms of Service",
  effectiveDate: "[EFFECTIVE DATE]",
  sections: [
    {
      heading: "1. Agreement to Terms",
      paragraphs: [
        "These Terms of Service (\"Terms\") are a binding agreement between PropWise AI (\"we,\" \"us,\" or \"our\") and the property management organization or individual that creates an account (\"Customer,\" \"you,\" or \"your\") to access the PropWise AI property management platform (the \"Service\"). By creating an account or using the Service, you accept these Terms on behalf of yourself and, if applicable, the organization you represent.",
      ],
    },
    {
      heading: "2. Description of the Service",
      paragraphs: [
        "PropWise AI is a software-as-a-service platform for residential property management, including property and unit records, lease and e-signature workflows, maintenance ticket tracking and vendor dispatch, rent collection, tenant screening request tracking, resident and staff communications, AI-assisted features, and financial reporting.",
        "AI Features. The Service includes features powered by third-party artificial intelligence models. These are decision-support tools, not a substitute for your own professional, financial, or legal judgment. Any confidence score, risk score, or recommendation is a computed estimate that may be incomplete, outdated, or wrong. You are solely responsible for reviewing and independently verifying any AI-generated output before relying on it.",
      ],
    },
    {
      heading: "3. Accounts",
      paragraphs: [
        "You are responsible for all activity under your organization's account, including activity by staff members you invite. Residents you give access to a resident portal must be given accurate information to enable their access. You must keep your login credentials confidential.",
      ],
    },
    {
      heading: "4. Free Trial, Fees, and Payment",
      paragraphs: [
        "New organization accounts may begin with a free trial period. Continued access after the trial requires an active paid subscription, billed in advance on a recurring basis through Stripe. Fees are non-refundable except as expressly stated or required by law. If a payment fails and is not cured, we may suspend access until payment is resolved.",
      ],
    },
    {
      heading: "5. Acceptable Use",
      paragraphs: [
        "You agree not to use the Service to violate fair housing law, the Fair Credit Reporting Act, landlord-tenant law, or consumer protection law; to discriminate against any applicant or resident on the basis of a protected characteristic; to send communications in violation of the TCPA or CAN-SPAM Act; or to attempt unauthorized access to the Service or other organizations' data.",
      ],
    },
    {
      heading: "6. Tenant Screening and Consumer Report Data",
      paragraphs: [
        "PropWise AI is not a consumer reporting agency. The Service provides a workspace for you to track tenant screening requests and applicant-provided data. If you obtain a consumer report about an applicant, you — not PropWise AI — are the \"user of consumer reports\" under the Fair Credit Reporting Act and are solely responsible for obtaining required consent, having a permissible purpose, providing required adverse-action notices, and complying with applicable state tenant-screening law.",
      ],
    },
    {
      heading: "7. Customer Data",
      paragraphs: [
        "You retain all ownership rights in the data you and your residents submit to the Service (\"Customer Data\"). You grant us a limited license to host, process, and transmit Customer Data solely to provide the Service, including sending relevant data to our subprocessors for that purpose. You are solely responsible for the accuracy, quality, and legality of Customer Data.",
      ],
    },
    {
      heading: "8. Disclaimers and Limitation of Liability",
      paragraphs: [
        "THE SERVICE IS PROVIDED \"AS IS\" WITHOUT WARRANTY OF ANY KIND. WE DO NOT WARRANT THE ACCURACY OF AI-GENERATED OUTPUT OR THAT USE OF THE SERVICE WILL SATISFY YOUR OBLIGATIONS UNDER FAIR HOUSING LAW, THE FCRA, OR ANY OTHER LAW. OUR TOTAL LIABILITY ARISING OUT OF THESE TERMS WILL NOT EXCEED THE AMOUNT YOU PAID US IN THE TWELVE MONTHS PRECEDING THE CLAIM.",
      ],
    },
    {
      heading: "9. Indemnification",
      paragraphs: [
        "You agree to indemnify and hold us harmless from any claim arising out of your use of the Service in violation of these Terms or applicable law, or your dealings with your residents, applicants, staff, or vendors.",
      ],
    },
    {
      heading: "10. Termination",
      paragraphs: [
        "You may cancel at any time through your account settings, effective at the end of your current billing period. We may suspend or terminate access for material breach, including non-payment. Upon termination, we will make Customer Data available for export for a reasonable period.",
      ],
    },
    {
      heading: "11. Changes to These Terms",
      paragraphs: [
        "We may update these Terms from time to time. We will provide reasonable notice of material changes before they take effect.",
      ],
    },
    {
      heading: "12. Contact",
      paragraphs: [
        "Questions about these Terms can be sent to [support@yourdomain.com].",
      ],
    },
  ],
};

export const PRIVACY_POLICY = {
  title: "Privacy Policy",
  effectiveDate: "[EFFECTIVE DATE]",
  sections: [
    {
      heading: "1. Who This Policy Covers",
      paragraphs: [
        "This Privacy Policy explains how PropWise AI collects, uses, and shares personal information through the PropWise AI property management platform. It applies to staff and owner users at a subscribing organization, residents given access to a resident portal, and prospective tenants who submit information through a leasing or screening workflow.",
      ],
    },
    {
      heading: "2. Information We Collect",
      paragraphs: [
        "Account information (name, email, phone, hashed password, role); property and lease data entered by staff; tenant screening data where a Customer uses that feature (credit, income, rental history, and supporting documents — see Section 6); payment references from our processor, Stripe (we do not store full card or bank numbers); communications content and metadata (in-app messages, email, SMS, call recordings/transcripts for after-hours maintenance calls); uploaded photos and documents; and usage/device data such as IP address and browser type.",
      ],
    },
    {
      heading: "3. How We Use Information",
      paragraphs: [
        "To provide and improve the Service, process payments, send transactional communications on a Customer's behalf, power AI-assisted features, detect and prevent abuse, comply with legal obligations, and communicate with you about the Service.",
      ],
    },
    {
      heading: "4. How We Share Information",
      paragraphs: [
        "We do not sell personal information. We share it with the Customer organization managing your property, with service providers who process data on our behalf (see the subprocessor table below), with law enforcement or regulators where legally required, and with a successor entity in a merger or acquisition.",
      ],
    },
    {
      heading: "5. AI-Powered Features",
      paragraphs: [
        "The Service uses a third-party AI model provider (currently Anthropic) to power features such as automated recommendations and document extraction. Relevant context needed to answer a specific request is sent to that provider to generate a response. Resident-identifying information is deliberately withheld from certain AI features where it isn't needed for the task.",
      ],
    },
    {
      heading: "6. Tenant Screening Data — Additional Protections",
      paragraphs: [
        "Consumer report data obtained through the screening feature is used solely to support the Customer's own screening process, is not used to train AI models, and is not used for any purpose unrelated to that screening request. PropWise AI is not a consumer reporting agency.",
      ],
    },
    {
      heading: "7. Subprocessors",
      paragraphs: [
        "The table below lists our current subprocessors — third parties who process personal information on our behalf.",
      ],
      table: SUBPROCESSORS,
    },
    {
      heading: "8. Data Retention and Security",
      paragraphs: [
        "We retain personal information for as long as the associated account remains active, plus a reasonable period afterward for data export, and as needed for legal and accounting obligations. We use encryption in transit, irreversible password hashing, role-based access controls, per-organization data isolation, and rate limiting to protect personal information. No system is completely secure.",
      ],
    },
    {
      heading: "9. Your Rights",
      paragraphs: [
        "Depending on your location, you may have rights to access, correct, delete, or receive a copy of your personal information. Residents and applicants should contact the property management organization they interact with directly; we will assist that organization in responding to your request.",
      ],
    },
    {
      heading: "10. Contact Us",
      paragraphs: [
        "Questions about this Policy can be sent to [privacy@yourdomain.com].",
      ],
    },
  ],
};
