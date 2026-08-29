import type { Locale } from "@/lib/i18n";

export interface LegalSection {
  title: string;
  body: string[];
}

export interface LegalPage {
  title: string;
  intro: string;
  updated: string;
  sections: LegalSection[];
}

export interface LegalContent {
  terms: LegalPage;
  privacy: LegalPage;
}

const en: LegalContent = {
  terms: {
    title: "Terms of Service",
    intro:
      "These Terms of Service govern your use of the SILKDEV website and services. By using this website, the AI intake assistant, or the client portal, you agree to these terms.",
    updated: "Last updated: August 7, 2026",
    sections: [
      {
        title: "1. Who we are",
        body: [
          "Silkdev-SUARL (matricule fiscal 1782006M) is a software design and development studio based in Menzel Bourguiba, Tunisia (bureau 5, centre Aziza, 1er étage, Av. de l'Indépendance, Menzel Bourguiba 7050). You can reach us at contact@silkdev.com.tn.",
        ],
      },
      {
        title: "2. Our services",
        body: [
          "We provide web design and development, AI and agent pipeline engineering, API and platform development, and fractional CTO services. We also build products, including SILKLEARN.",
          "We do not publish fixed prices. Every project is scoped individually and quoted at a fixed price after we understand your needs.",
        ],
      },
      {
        title: "3. AI assistants",
        body: [
          "The AI intake assistant helps you shape a project brief through conversation. Information you share may be processed by third-party large language model providers to generate responses. The final brief is reviewed and submitted by you before it reaches us.",
          "Once your project is active, the client portal includes an AI project representative that answers questions about your project and may add tasks to your planner or store notes about your preferences so future conversations are more helpful.",
          "AI-generated responses are informational and may be imperfect. Do not rely on them as professional, legal, or financial advice, and do not share sensitive personal data (such as health, financial, or identification numbers) through the chat. We are not liable for information you volunteer.",
        ],
      },
      {
        title: "4. Your responsibilities",
        body: [
          "You agree to provide accurate information and to use the website, chat, and portal lawfully. You must not submit unlawful, infringing, or malicious content.",
        ],
      },
      {
        title: "5. Quotes, payments, and delivery",
        body: [
          "Each engagement begins with a written proposal: scope, fixed price, and timeline. Payment terms are agreed per project. Where we offer online payment, transactions are processed by Konnect (Global Net International) in Tunisia; we never see or store your card details. Intellectual property in deliverables transfers to you upon full payment; until then we retain rights to the work product.",
        ],
      },
      {
        title: "6. Confidentiality",
        body: [
          "We treat the briefs, projects, and materials you share as confidential and use them only to deliver our services.",
        ],
      },
      {
        title: "7. Limitation of liability",
        body: [
          "To the maximum extent permitted by law, Silkdev-SUARL is not liable for indirect, incidental, or consequential damages arising from your use of the website, the AI assistant, or our services. Our total liability for any claim is limited to the amount you paid us for the relevant project in the twelve months preceding the claim.",
        ],
      },
      {
        title: "8. Changes to these terms",
        body: [
          "We may update these terms from time to time. The updated version will be published on this page with a new revision date.",
        ],
      },
      {
        title: "10. Governing law",
        body: [
          "These terms are governed by the laws of the Republic of Tunisia. Any dispute arising out of or in connection with these terms shall be subject to the exclusive jurisdiction of the competent courts of Tunisia.",
        ],
      },
      {
        title: "11. Contact",
        body: [
          "Questions about these terms? Email contact@silkdev.com.tn.",
        ],
      },
    ],
  },
  privacy: {
    title: "Privacy Policy",
    intro:
      "This policy explains what data Silkdev-SUARL collects, why we collect it, and how you can exercise your rights.",
    updated: "Last updated: August 7, 2026",
    sections: [
      {
        title: "1. Data we collect",
        body: [
          "When you use the intake form or the AI chat assistant, we collect the information you provide: your name, company, email, phone, project category, description, budget range, and timeline.",
          "When you submit a brief, we store the brief and the conversation transcript so we can review and respond.",
          "We use browser localStorage to remember your in-progress chat session on your own device.",
          "If you create a portal account, we store your account credentials (securely hashed), your projects, and your briefs.",
          "The client portal includes an AI project representative. Project chat messages are used to answer your questions, and preferences or context you confirm during those conversations may be saved to your client profile so future chats are more helpful.",
          "If you pay online, payments are processed by Konnect (Global Net International). We never see or store your card details; Konnect handles the payment data under its own privacy terms.",
          "Cloudflare Turnstile performs a bot check on the intake flow, and Cloudflare also provides content delivery and protection for this website; these services may process technical data such as your IP address and browser fingerprint.",
        ],
      },
      {
        title: "2. How we use your data",
        body: [
          "To respond to your inquiries and prepare quotes.",
          "To deliver the services you request and manage your project in the client portal.",
          "To operate, secure, and improve the website.",
          "We do not sell your personal data.",
        ],
      },
      {
        title: "3. Legal bases",
        body: [
          "We process your data on the basis of your consent (when you submit a brief), the performance of a contract (when you engage us), and our legitimate interests in operating and securing the website.",
          "We comply with Tunisian Law No. 2004-63 on the protection of personal data (and its implementing texts), and with the GDPR where it applies to you as a resident of the European Economic Area.",
        ],
      },
      {
        title: "4. Third parties",
        body: [
          "Vercel Inc. hosts the website and its data stores.",
          "Cloudflare, Inc. provides content delivery, DDoS protection, and the Turnstile bot check.",
          "Konnect (Global Net International, Tunisia) processes online payments; it does not share your card details with us.",
          "Zoho (ZeptoMail) sends transactional emails such as brief confirmations, project updates, and password resets.",
          "Google Analytics (Google LLC) measures site usage through analytics cookies — loaded only after you accept the cookie banner; you can decline and no analytics load at all.",
          "Third-party large language model providers process chat messages to power the AI assistant. Responses are generated automatically; your messages may transit through these providers.",
          "If you book a discovery call, calendar and email providers process the booking details.",
        ],
      },
      {
        title: "5. Cookies and local storage",
        body: [
          "We use a minimal cookie banner and browser localStorage for your chat session. We do not use advertising cookies. Google Analytics cookies are loaded only after you accept the banner, and we anonymize IP addresses. Cloudflare Turnstile may set its own cookies required for bot detection.",
        ],
      },
      {
        title: "6. Data retention",
        body: [
          "Briefs and project records are kept for as long as needed to deliver and document our services, and afterwards as required by applicable law. Chat transcripts are kept with the brief they belong to. You may request deletion at any time.",
        ],
      },
      {
        title: "7. Your rights",
        body: [
          "Depending on your jurisdiction, you may have the right to access, correct, delete, or port your personal data, and to object to or restrict processing. This includes the rights granted by Tunisian Law No. 2004-63 (exercisable through the INPDP) and, if you are in the EEA, the GDPR. To exercise these rights, email contact@silkdev.com.tn and we will respond within the timeframe required by law.",
        ],
      },
      {
        title: "8. International transfers",
        body: [
          "Our hosting and processing providers may operate outside your country, including the United States and the European Union. Where required, transfers are based on standard contractual clauses or equivalent safeguards.",
        ],
      },
      {
        title: "9. Security",
        body: [
          "We use HTTPS, secure session management (better-auth), and platform security features from our hosting providers. No method of transmission is 100% secure; we cannot guarantee absolute security.",
        ],
      },
      {
        title: "10. Contact",
        body: [
          "Privacy questions or requests: contact@silkdev.com.tn, Silkdev-SUARL, bureau 5, centre Aziza, 1er étage, Av. de l'Indépendance, Menzel Bourguiba 7050, Tunisia.",
        ],
      },
    ],
  },
};

const fr: LegalContent = {
  terms: {
    title: "Conditions d'utilisation",
    intro:
      "Les présentes conditions régissent votre utilisation du site et des services de SILKDEV. En utilisant ce site, l'assistant d'accueil IA ou le portail client, vous acceptez ces conditions.",
    updated: "Dernière mise à jour : 7 août 2026",
    sections: [
      {
        title: "1. Qui sommes-nous",
        body: [
          "Silkdev-SUARL est un studio de conception et de développement logiciel basé à Menzel Bourguiba, Tunisie (bureau 5, centre Aziza, 1er étage, Av. de l'Indépendance, Menzel Bourguiba 7050). Contact : contact@silkdev.com.tn.",
        ],
      },
      {
        title: "2. Nos services",
        body: [
          "Nous fournissons la conception et le développement web, l'ingénierie de pipelines IA et d'agents, le développement d'API et de plateformes, ainsi que des services de CTO à temps partagé. Nous développons également des produits, dont SILKLEARN.",
          "Nous ne publions pas de prix fixes. Chaque projet est évalué individuellement et fait l'objet d'un devis à prix fixe après compréhension de vos besoins.",
        ],
      },
      {
        title: "3. Assistants IA",
        body: [
          "L’assistant d’accueil IA vous aide à structurer un brief de projet par conversation. Les informations partagées peuvent être traitées par des fournisseurs tiers de modèles de langage pour générer des réponses. Le brief final est relu et soumis par vous avant de nous parvenir.",
          "Une fois votre projet actif, le portail client comprend un représentant IA du projet qui répond à vos questions, peut ajouter des tâches à votre planificateur ou enregistrer des notes sur vos préférences afin que les futures conversations soient plus utiles.",
          "Les réponses générées par l’IA sont informatives et peuvent être imparfaites. Ne vous y fiez pas comme à un conseil professionnel, juridique ou financier, et ne partagez pas de données personnelles sensibles (santé, finances, numéros d’identification) via le chat. Nous ne sommes pas responsables des informations que vous divulguez volontairement.",
        ],
      },
      {
        title: "4. Vos responsabilités",
        body: [
          "Vous vous engagez à fournir des informations exactes et à utiliser le site, le chat et le portail de manière licite. Vous ne devez pas soumettre de contenu illégal, contrefaisant ou malveillant.",
        ],
      },
      {
        title: "5. Devis, paiements et livraison",
        body: [
          "Chaque engagement commence par une proposition écrite : périmètre, prix fixe et calendrier. Les conditions de paiement sont convenues par projet. La propriété intellectuelle des livrables vous est transférée après paiement intégral. Lorsque nous proposons le paiement en ligne, les transactions sont traitées par Konnect (Global Net International) en Tunisie ; nous ne voyons ni ne stockons jamais vos données de carte. Jusqu'alors, nous conservons des droits sur le travail produit.",
        ],
      },
      {
        title: "6. Confidentialité",
        body: [
          "Nous traitons les briefs, projets et documents partagés comme confidentiels et les utilisons uniquement pour fournir nos services.",
        ],
      },
      {
        title: "7. Limitation de responsabilité",
        body: [
          "Dans la mesure maximale permise par la loi, Silkdev-SUARL n'est pas responsable des dommages indirects, accessoires ou consécutifs découlant de l'utilisation du site, de l'assistant IA ou de nos services. Notre responsabilité totale est limitée au montant que vous nous avez payé pour le projet concerné au cours des douze mois précédant la réclamation.",
        ],
      },
      {
        title: "8. Modifications des conditions",
        body: [
          "Nous pouvons mettre à jour ces conditions. La version actualisée sera publiée sur cette page avec une nouvelle date de révision.",
        ],
      },
      {
        title: "10. Droit applicable",
        body: [
          "Les présentes conditions sont régies par le droit de la République tunisienne. Tout litige relatif à ces conditions relève de la compétence exclusive des tribunaux tunisiens.",
        ],
      },
      {
        title: "11. Contact",
        body: ["Des questions ? Écrivez-nous à contact@silkdev.com.tn."],
      },
    ],
  },
  privacy: {
    title: "Politique de confidentialité",
    intro:
      "Cette politique explique quelles données Silkdev-SUARL collecte, pourquoi, et comment exercer vos droits.",
    updated: "Dernière mise à jour : 7 août 2026",
    sections: [
      {
        title: "1. Données collectées",
        body: [
          "Lorsque vous utilisez le formulaire ou l'assistant de chat IA, nous collectons les informations que vous fournissez : nom, entreprise, e-mail, téléphone, catégorie de projet, description, fourchette budgétaire et calendrier.",
          "Lorsque vous soumettez un brief, nous stockons le brief et la transcription de la conversation pour pouvoir y répondre.",
          "Nous utilisons le stockage local du navigateur pour mémoriser votre session de chat en cours sur votre appareil.",
          "Si vous créez un compte portail, nous stockons vos identifiants (hachés de manière sécurisée), vos projets et vos briefs.",
          "Le portail client comprend un représentant IA du projet. Les messages de chat du projet sont utilisés pour répondre à vos questions, et les préférences ou le contexte que vous confirmez lors de ces conversations peuvent être enregistrés dans votre profil client afin que les futurs échanges soient plus utiles.",
          "Si vous payez en ligne, les paiements sont traités par Konnect (Global Net International). Nous ne voyons ni ne stockons jamais vos données de carte ; Konnect gère ces données selon ses propres conditions de confidentialité.",
          "Cloudflare Turnstile effectue une vérification anti-robots sur le parcours d'accueil, et Cloudflare assure également la diffusion et la protection de ce site ; ces services peuvent traiter des données techniques telles que votre adresse IP et l'empreinte du navigateur.",
        ],
      },
      {
        title: "2. Utilisation de vos données",
        body: [
          "Pour répondre à vos demandes et préparer des devis.",
          "Pour fournir les services demandés et gérer votre projet dans le portail client.",
          "Pour exploiter, sécuriser et améliorer le site.",
          "Nous ne vendons pas vos données personnelles.",
        ],
      },
      {
        title: "3. Bases légales",
        body: [
          "Nous traitons vos données sur la base de votre consentement (soumission d'un brief), de l'exécution d'un contrat (engagement) et de nos intérêts légitimes dans l'exploitation et la sécurité du site.",
          "Nous nous conformons à la loi tunisienne n° 2004-63 relative à la protection des données personnelles (et à ses textes d'application), ainsi qu'au RGPD lorsqu'il s'applique à vous en tant que résident de l'Espace économique européen.",
        ],
      },
      {
        title: "4. Tiers",
        body: [
          "Vercel Inc. héberge le site et ses données.",
          "Cloudflare, Inc. fournit la diffusion de contenu, la protection anti-DDoS et la vérification anti-robots Turnstile.",
          "Konnect (Global Net International, Tunisie) traite les paiements en ligne ; il ne nous communique jamais vos données de carte.",
          "Zoho (ZeptoMail) envoie les e-mails transactionnels tels que les confirmations de brief, les mises à jour de projet et les réinitialisations de mot de passe.",
          "Google Analytics (Google LLC) mesure l'utilisation du site via des cookies d'analyse — chargés uniquement après acceptation de la bannière de cookies ; vous pouvez refuser et aucun suivi n'est chargé.",
          "Des fournisseurs tiers de modèles de langage traitent les messages du chat pour alimenter l'assistant IA.",
          "Si vous réservez un appel de découverte, les fournisseurs de calendrier et d'e-mail traitent les détails de la réservation.",
        ],
      },
      {
        title: "5. Cookies et stockage local",
        body: [
          "Nous utilisons un bandeau de cookies minimal et le stockage local du navigateur pour votre session de chat. Nous n'utilisons pas de cookies publicitaires. Les cookies Google Analytics ne sont chargés qu'après acceptation de la bannière, et nous anonymisons les adresses IP. Cloudflare Turnstile peut définir ses propres cookies nécessaires à la détection des robots.",
        ],
      },
      {
        title: "6. Conservation des données",
        body: [
          "Les briefs et dossiers de projet sont conservés aussi longtemps que nécessaire pour fournir et documenter nos services, puis selon les exigences légales. Les transcriptions de chat sont conservées avec le brief correspondant. Vous pouvez demander leur suppression à tout moment.",
        ],
      },
      {
        title: "7. Vos droits",
        body: [
          "Selon votre juridiction, vous pouvez avoir le droit d'accéder à vos données, de les corriger, de les supprimer ou de les porter, et de vous opposer à leur traitement. Cela inclut les droits conférés par la loi tunisienne n° 2004-63 (exerçables auprès de l'INPDP) et, si vous êtes dans l'EEE, le RGPD. Pour exercer ces droits, écrivez à contact@silkdev.com.tn.",
        ],
      },
      {
        title: "8. Transferts internationaux",
        body: [
          "Nos fournisseurs d'hébergement et de traitement peuvent opérer hors de votre pays, notamment aux États-Unis et dans l'Union européenne. Les transferts reposent sur des clauses contractuelles types ou des garanties équivalentes.",
        ],
      },
      {
        title: "9. Sécurité",
        body: [
          "Nous utilisons HTTPS, une gestion de session sécurisée (better-auth) et les fonctions de sécurité de nos hébergeurs. Aucune transmission n'est 100 % sécurisée.",
        ],
      },
      {
        title: "10. Contact",
        body: [
          "Questions ou demandes : contact@silkdev.com.tn, Silkdev-SUARL, bureau 5, centre Aziza, 1er étage, Av. de l'Indépendance, Menzel Bourguiba 7050, Tunisie.",
        ],
      },
    ],
  },
};

export const legalContent: Record<Locale, LegalContent> = { en, fr };
