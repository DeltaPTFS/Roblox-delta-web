(() => {
  "use strict";
  const form = document.getElementById("owner-longform-news-form");
  if (!form) return;
  const body = form.querySelector("#longform-news-body");
  const words = form.querySelector("[data-news-words]");
  const counter = document.getElementById("longform-news-count");
  const submit = form.querySelector("[data-news-submit]");
  const count = () => {
    const total = body.value.trim().split(/\s+/u).filter(Boolean).length;
    words.textContent = total.toLocaleString("en-US");
    const tooLong = total > 10000;
    counter.classList.toggle("is-over", tooLong);
    body.setCustomValidity(tooLong ? "Limit your article to 10,000 words." : "");
    submit.disabled = tooLong || total === 0;
  };
  body.addEventListener("input", count);
  form.addEventListener("submit", e => {
    count();
    if (!form.checkValidity()) {
      e.preventDefault();
      form.reportValidity();
    }
  });
  count();
})();