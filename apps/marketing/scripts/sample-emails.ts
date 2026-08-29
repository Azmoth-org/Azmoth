import { briefClientTemplate, resetPasswordTemplate } from "../src/lib/emailTemplates";

const a = briefClientTemplate({ name: "Sara Ben Ali", ref: "SD-1001" });
const b = resetPasswordTemplate({ url: "https://silkdev.com.tn/en/reset-password?token=example" });

import { writeFileSync } from "fs";
writeFileSync("/tmp/sample-brief-confirmation.html", a);
writeFileSync("/tmp/sample-password-reset.html", b);
console.log("written:", a.length, b.length);
