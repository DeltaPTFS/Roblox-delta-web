/* Owner / Admin / Staff workspace controller.
 * Existing FastAPI forms and role permissions stay unchanged.
 * Without JavaScript, all sections remain visible and all anchors work.
 */
(() => {
  "use strict";
  const shell = document.querySelector('[data-ops-workspace]');
  if (!shell) return;

  const tabs = [...shell.querySelectorAll('.ops-workspace-nav [data-ops-tab]')];
  const sections = [...shell.querySelectorAll(':scope > [data-ops-group]')];
  if (!tabs.length || !sections.length) return;

  const allowed = new Set(tabs.map(tab => tab.dataset.opsTab));

  function groupForHash() {
    const hash = decodeURIComponent(location.hash.substring(1));
    if (hash) {
      const target = document.getElementById(hash);
      const section = target?.closest('[data-ops-group]');
      if (section && allowed.has(section.dataset.opsGroup)) {
        return section.dataset.opsGroup;
      }
    }
    // An incoming search or directory pagination result must remain accessible.
    const params = new URLSearchParams(location.search);
    if ((params.has('q') || params.has('directory_page')) && allowed.has('members')) {
      return 'members';
    }
    if ((params.has('flight_created') || params.has('flight_id')) && allowed.has('flights')) {
      return 'flights';
    }
    if ((params.has('announcement_saved') || params.has('announcement_removed')) && allowed.has('announcements')) {
      return 'announcements';
    }
    return 'overview';
  }

  function openNestedDetails(target) {
    const parents = [];
    let parent = target?.parentElement;
    while (parent && parent !== shell) {
      if (parent.tagName === 'DETAILS') parents.push(parent);
      parent = parent.parentElement;
    }
    parents.forEach(item => { item.open = true; });
  }

  function activate(group, navigate = false) {
    if (!allowed.has(group)) group = 'overview';
    for (const section of sections) {
      section.hidden = section.dataset.opsGroup !== group;
    }
    for (const tab of tabs) {
      if (tab.dataset.opsTab === group) {
        tab.setAttribute('aria-current', 'page');
      } else {
        tab.removeAttribute('aria-current');
      }
    }
    shell.dataset.opsReady = 'true';
    shell.dataset.opsActive = group;
    if (navigate) {
      const preferred = tabs.find(tab => tab.dataset.opsTab === group)?.getAttribute('href');
      const target = preferred && preferred[0] === '#' ? document.getElementById(preferred.slice(1)) : null;
      if (preferred) history.pushState(null, '', preferred);
      if (target) {
        openNestedDetails(target);
        target.scrollIntoView({block: 'start', behavior: 'instant'});
      } else {
        shell.querySelector('.ops-workspace-nav')?.scrollIntoView({block:'start', behavior:'instant'});
      }
    }
  }

  function makeDetails(container, label, expanded = false) {
    if (!container || container.querySelector(':scope > details.ops-hidden-tools')) return;
    const details = document.createElement('details');
    details.className = 'ops-hidden-tools';
    details.open = expanded;
    const summary = document.createElement('summary');
    summary.textContent = label;
    details.append(summary);
    while (container.children.length) {
      details.append(container.children[0]);
    }
    container.append(details);
  }

  // Show one member summary at a time, with actions available on demand.
  const query = new URLSearchParams(location.search).get('q');
  const members = [...shell.querySelectorAll('.delta-admin-member-actions > .admin-member')];
  members.forEach((member, index) => {
    const identity = member.querySelector(':scope > .identity');
    if (!identity) return;
    const wrapper = document.createElement('div');
    wrapper.className = 'ops-member-advanced';
    const details = document.createElement('details');
    details.className = 'ops-member-detail';
    const summary = document.createElement('summary');
    summary.innerHTML = '<span>Member actions &amp; history</span><span aria-hidden="true">+</span>';
    details.append(summary);
    while (identity.nextSibling) details.append(identity.nextSibling);
    wrapper.append(details);
    member.append(wrapper);
    // A user specifically searched for an account: show the first match's tools.
    if (query && index === 0) details.open = true;
  });

  // Collapse rarely-used, long logs but preserve the ability to expand every row.
  const archive = shell.querySelector('.flight-archive');
  const logs = shell.querySelectorAll('.ownership-logs, .feedback-admin');
  const collapseBody = (section, title) => {
    if (!section) return;
    const children = [...section.children];
    const body = document.createElement('div');
    body.className = 'ops-archive-content';
    for (const child of children) {
      if (['SPAN','H2'].includes(child.tagName) || child.classList.contains('eyebrow')) continue;
      if (child.tagName === 'P' && child.previousElementSibling?.tagName === 'H2') continue;
      body.append(child);
    }
    if (!body.children.length) return;
    makeDetails(body, title);
    section.append(body);
  };
  collapseBody(archive, 'View archived flights');
  logs.forEach(section => {
    const name = section.querySelector('h2')?.textContent?.trim() || 'History';
    collapseBody(section, 'View ' + name.toLowerCase());
  });

  tabs.forEach(tab => tab.addEventListener('click', event => {
    event.preventDefault();
    activate(tab.dataset.opsTab, true);
  }));
  window.addEventListener('hashchange', () => {
    const group = groupForHash();
    activate(group);
    const hash = decodeURIComponent(location.hash.substring(1));
    const target = hash && document.getElementById(hash);
    if (target && !target.hidden) {
      openNestedDetails(target);
      target.scrollIntoView({block:'start'});
    }
  });

  activate(groupForHash());
  if (location.hash) {
    const target = document.getElementById(decodeURIComponent(location.hash.substring(1)));
    if (target) {
      openNestedDetails(target);
      requestAnimationFrame(() => target.scrollIntoView({block:'start'}));
    }
  }
})();