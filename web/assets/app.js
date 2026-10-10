/* Taste The Whip — chord toggle + lyric search. No dependencies. */
(function () {
  'use strict';

  // ── remembered preferences (private windows can throw on access) ──
  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  };

  // ── chord toggle ──────────────────────────────────────
  var btn = document.querySelector('[data-chordtoggle]');
  function applyChords(on) {
    document.body.classList.toggle('nochords', !on);
    if (btn) {
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
      btn.querySelector('.lbl').textContent = on ? 'Chords' : 'Chords off';
    }
  }
  if (btn) {
    applyChords(store.get('ttw-chords') !== 'off');
    btn.addEventListener('click', function () {
      var on = btn.getAttribute('aria-pressed') !== 'true';
      applyChords(on);
      store.set('ttw-chords', on ? 'on' : 'off');
    });
  }

  // ── chord popovers: tap a chord name in the lyrics for its shape ──
  (function () {
    var grid = document.querySelector('.cd-grid');
    if (!grid) return;
    var shapes = {};
    [].forEach.call(grid.querySelectorAll('.cd-card'), function (c) {
      shapes[c.dataset.shape] = c.querySelector('svg');
    });
    var pop = null, openFor = null;

    function close() {
      if (pop) { pop.remove(); pop = null; }
      if (openFor) { openFor.classList.remove('on'); openFor = null; }
      [].forEach.call(grid.querySelectorAll('.lit'), function (c) {
        c.classList.remove('lit');
      });
    }

    function open(el) {
      var name = el.dataset.c, svg = shapes[name];
      if (!svg) return;
      close();
      pop = document.createElement('figure');
      pop.className = 'cd-pop';
      pop.appendChild(svg.cloneNode(true));
      var cap = document.createElement('figcaption');
      cap.textContent = name;
      pop.appendChild(cap);
      document.body.appendChild(pop);

      // place above the chord, flipping below if it would clip the top
      var r = el.getBoundingClientRect();
      var pw = pop.offsetWidth, ph = pop.offsetHeight;
      var left = r.left + window.scrollX + r.width / 2 - pw / 2;
      left = Math.max(8, Math.min(left, window.innerWidth - pw - 8 + window.scrollX));
      var top = r.top + window.scrollY - ph - 8;
      if (r.top - ph - 8 < 0) top = r.bottom + window.scrollY + 8;
      pop.style.left = left + 'px';
      pop.style.top = top + 'px';

      el.classList.add('on');
      openFor = el;
      var card = grid.querySelector('.cd-card[data-shape="' + name + '"]');
      if (card) card.classList.add('lit');
    }

    document.addEventListener('click', function (ev) {
      var el = ev.target.closest ? ev.target.closest('.lyrics .ch') : null;
      if (el) {
        ev.preventDefault();
        if (openFor === el) { close(); } else { open(el); }
      } else if (!ev.target.closest || !ev.target.closest('.cd-pop')) {
        close();
      }
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') close();
      if ((ev.key === 'Enter' || ev.key === ' ') &&
          ev.target.classList && ev.target.classList.contains('ch')) {
        ev.preventDefault();
        if (openFor === ev.target) { close(); } else { open(ev.target); }
      }
    });
    window.addEventListener('resize', close);
    window.addEventListener('scroll', close, { passive: true });
  })();

  // ── click-to-play: swap the facade for the real embed ──
  [].forEach.call(document.querySelectorAll('.playerbox'), function (box) {
    var btn = box.querySelector('.playbtn');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var src = box.dataset.embed;
      if (!src) return;
      src += (src.indexOf('?') < 0 ? '?' : '&') + 'auto_play=true';
      src = src.replace(/auto_play=false/g, 'auto_play=true');
      var f = document.createElement('iframe');
      f.className = 'player';
      f.width = '100%';
      f.height = box.dataset.h || '140';
      f.scrolling = 'no';
      f.frameBorder = 'no';
      f.allow = 'autoplay';
      f.title = btn.getAttribute('aria-label') || 'Player';
      f.src = src;
      box.classList.add('playing');
      btn.replaceWith(f);
    });
  });

  // ── search (songs.html) ───────────────────────────────
  var q = document.getElementById('q');
  if (q && window.SONGS) {
    var rows = {}, order = [];
    [].forEach.call(document.querySelectorAll('.srow'), function (li) {
      rows[li.dataset.slug] = li;
      order.push(li.dataset.slug);
    });
    var byslug = {};
    window.SONGS.forEach(function (s) { byslug[s.s] = s; });

    var clear = document.getElementById('qclear');
    var count = document.getElementById('qcount');
    var none = document.getElementById('noresults');
    var total = order.length;

    function esc(s) {
      return s.replace(/[&<>"]/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
      });
    }
    function rx(term) {
      return new RegExp(term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'ig');
    }
    function mark(text, term) {
      return esc(text).replace(rx(term), function (m) { return '<mark>' + m + '</mark>'; });
    }

    function snippet(lyr, term) {
      var i = lyr.toLowerCase().indexOf(term.toLowerCase());
      if (i < 0) return '';
      // widen to the surrounding lyric line
      var from = lyr.lastIndexOf(' / ', i), to = lyr.indexOf(' / ', i + term.length);
      from = from < 0 ? 0 : from + 3;
      to = to < 0 ? lyr.length : to;
      var line = lyr.slice(from, to).trim();
      if (line.length > 150) {
        var p = Math.max(0, i - from - 50);
        line = (p > 0 ? '…' : '') + line.slice(p, p + 150).trim() + '…';
      }
      return '&ldquo;' + mark(line, term) + '&rdquo;';
    }

    function run() {
      var term = q.value.trim();
      if (clear) clear.hidden = !term;
      var shown = 0;

      order.forEach(function (slug) {
        var li = rows[slug], s = byslug[slug];
        var titleEl = li.querySelector('.t'), snipEl = li.querySelector('.snip');

        if (!term) {
          li.hidden = false;
          titleEl.textContent = s.t;
          snipEl.hidden = true;
          snipEl.innerHTML = '';
          shown++;
          return;
        }
        var t = term.toLowerCase();
        var inTitle = s.t.toLowerCase().indexOf(t) >= 0;
        var inAlbum = s.a.toLowerCase().indexOf(t) >= 0;
        var inLyric = s.l.toLowerCase().indexOf(t) >= 0;

        if (inTitle || inAlbum || inLyric) {
          li.hidden = false;
          shown++;
          titleEl.innerHTML = inTitle ? mark(s.t, term) : esc(s.t);
          if (inLyric && !inTitle) {
            snipEl.innerHTML = snippet(s.l, term);
            snipEl.hidden = false;
          } else {
            snipEl.hidden = true;
            snipEl.innerHTML = '';
          }
        } else {
          li.hidden = true;
        }
      });

      if (none) none.hidden = shown > 0;
      if (count) {
        count.textContent = !term
          ? total + ' songs'
          : shown + (shown === 1 ? ' match' : ' matches') + ' for “' + term + '”';
      }
    }

    q.addEventListener('input', run);
    if (clear) clear.addEventListener('click', function () { q.value = ''; run(); q.focus(); });
    run();

    // Enter with a single match jumps straight to it
    q.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Enter') return;
      var vis = order.filter(function (s) { return !rows[s].hidden; });
      if (vis.length >= 1) {
        var a = rows[vis[0]].querySelector('a');
        if (a) window.location.href = a.href;
      }
    });
  }

  // ── keyboard shortcuts ────────────────────────────────
  document.addEventListener('keydown', function (ev) {
    var tag = (ev.target.tagName || '').toLowerCase();
    var typing = tag === 'input' || tag === 'textarea' || ev.target.isContentEditable;

    if (ev.key === '/' && !typing && !ev.metaKey && !ev.ctrlKey) {
      if (q) { ev.preventDefault(); q.focus(); q.select(); }
      return;
    }
    if (ev.key === 'Escape' && q && document.activeElement === q) {
      q.value = '';
      q.dispatchEvent(new Event('input'));
      q.blur();
      return;
    }
    if (typing || ev.metaKey || ev.ctrlKey || ev.altKey) return;

    // ← / → walk through tracks on a song page
    if (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight') {
      var sel = ev.key === 'ArrowLeft' ? '.pn.prev' : '.pn.next';
      var link = document.querySelector(sel);
      if (link) window.location.href = link.href;
    }
  });
})();
