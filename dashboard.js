async function load() {
  const res = await fetch("data/latest.json", { cache: "no-store" });
  const d = await res.json();
  document.getElementById("window-label").textContent = d.window.label;
  const when = new Date(d.updated_at);
  document.getElementById("updated").textContent =
    "Updated " + when.toLocaleString("en-US", { timeZone: d.timezone });

  const p = d.product;
  const paid = d.paid || {};
  const e = d.email_push || {};

  const row = (el, items) => {
    el.innerHTML = items
      .map(
        ([v, l, danger]) =>
          `<div class="stat${danger ? " danger" : ""}"><b>${v}</b><span>${l}</span></div>`
      )
      .join("");
  };

  row(document.getElementById("stats"), [
    ["$" + paid.spend_50pct, "Spend"],
    [p.app_installs, "App installs"],
    [p.registrations_android, "Accounts · Android"],
    [p.registrations_ios, "Accounts · iOS"],
  ]);
  row(document.getElementById("stats-2"), [
    [p.trials, "Trial granted"],
    [p.desktop_sync, "Desktop sync"],
    [p.password_import, "Password import", p.password_import === 0],
    [p.tru8_usernames, "Tru8 user name"],
  ]);

  const max = Math.max(...d.daily.map((x) => x.installs), 1);
  document.getElementById("bars").innerHTML = d.daily
    .map(
      (x) =>
        `<div class="bar-wrap"><div class="bar" style="height:${Math.round(
          (x.installs / max) * 100
        )}%"></div><span>${x.label}</span></div>`
    )
    .join("");

  document.getElementById("daily-rows").innerHTML = d.daily
    .map(
      (x) =>
        `<tr><td>${x.day || x.label}</td><td class="num">${x.installs}</td><td class="num">${x.registrations}</td><td class="num">${x.trials}</td><td class="num">${x.tru8 ?? 0}</td></tr>`
    )
    .join("");

  document.getElementById("alerts").innerHTML = (d.alerts || [])
    .map((a) => `<li>${a}</li>`)
    .join("");

  document.getElementById("email-rows").innerHTML = `
    <tr><td>L8-01 email → registration</td><td class="num">${e.l801_delivered} delivered</td></tr>
    <tr><td>Onboarding received</td><td class="num">${e.onboarding_people} of ${p.registrations}</td></tr>
    <tr><td>Onboarding opened</td><td class="num">${e.onboarding_opened}</td></tr>
    <tr><td>Onboarding clicked</td><td class="num">${e.onboarding_clicked}</td></tr>
    <tr><td>Trial email opened</td><td class="num">${e.trial_email_opened}</td></tr>
    <tr><td>Push opened</td><td class="num">${e.push_opened}</td></tr>
  `;
}

load().catch((err) => {
  document.getElementById("window-label").textContent =
    "Could not load data/latest.json";
  console.error(err);
});
