import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import type { App } from '../app/context';
import { h, lazyImages } from './dom';
import { SECTIONS } from './tour-content';

gsap.registerPlugin(ScrollTrigger);

export interface Tour {
  el: HTMLElement;
  rail: HTMLElement;
  /** Scroll to a section. */
  goto(index: number, smooth: boolean): void;
  /** Call once the elements are in the document. */
  start(): void;
}

/**
 * The scroll tour: ten sections of text over the fixed stage.
 *
 * Scroll position is published as one number, `u = section index + progress
 * through that section` (0 when the section's top reaches the top of the
 * viewport, 1 when the next section's does). The scene scrubs its camera from
 * `app.tour`; `store.section` is the section whose panel is being read and
 * drives the top bar, the rail and the static plates.
 */
export function buildTour(app: App): Tour {
  const sections = SECTIONS.map((def, i) =>
    h(
      'section.tour-section',
      { id: `s${def.id}`, dataset: { index: String(i) }, 'aria-label': def.name },
      def.build(app),
    ),
  );
  sections[0]!.classList.add('tour-cover');
  const el = h('main.tour', { id: 'tour' }, sections);
  lazyImages(el);

  const marks = SECTIONS.map((def, i) =>
    h(
      'li',
      null,
      h(
        'button.rail-mark',
        { type: 'button', title: def.name, 'aria-label': `Section ${def.id}: ${def.name}`, onclick: () => goto(i, true) },
        h('span.data', null, def.id),
      ),
    ),
  );
  const rail = h('nav.rail', { 'aria-label': 'Sections' }, h('ol', null, marks));

  const progress = new Array<number>(sections.length).fill(0);
  const publish = () => {
    if (app.store.get().tab !== 'dossier') return;
    let u = 0;
    for (let i = 0; i < progress.length; i++) {
      if (progress[i]! > 0) u = i + Math.min(progress[i]!, 1);
    }
    app.tour.set(Math.min(u, sections.length - 1));
  };

  let triggers: ScrollTrigger[] = [];
  const arm = () => {
    for (const t of triggers) t.kill();
    triggers = [];
    sections.forEach((section, i) => {
      triggers.push(
        ScrollTrigger.create({
          trigger: section,
          start: 'top top',
          end: 'bottom top',
          onUpdate: (self) => {
            progress[i] = self.progress;
            publish();
          },
          onRefresh: (self) => {
            progress[i] = self.progress;
            publish();
          },
        }),
        ScrollTrigger.create({
          trigger: section,
          start: 'top 60%',
          end: 'bottom 60%',
          onToggle: (self) => {
            if (self.isActive && app.store.get().tab === 'dossier') app.store.set({ section: i });
          },
        }),
      );
    });
  };

  function goto(index: number, smooth: boolean): void {
    const target = sections[Math.min(sections.length - 1, Math.max(0, index))];
    if (!target) return;
    // One pixel past the top so the section's own trigger is the active one.
    const top = index === 0 ? 0 : target.offsetTop + 1;
    window.scrollTo({ top, behavior: smooth && !app.reducedMotion() ? 'smooth' : 'auto' });
  }

  app.store.watch(
    (s) => s.section,
    (index) => {
      marks.forEach((li, i) => {
        const b = li.firstElementChild as HTMLElement;
        if (i === index) b.setAttribute('aria-current', 'true');
        else b.removeAttribute('aria-current');
      });
    },
  );

  // Leaving the tour takes the text out of the page and locks scrolling;
  // coming back restores the place.
  let savedIndex = app.store.get().section;
  let armed = false;
  const start = () =>
    app.store.watch(
    (s) => s.tab === 'dossier',
    (inTour, was) => {
      if (inTour) {
        document.documentElement.classList.remove('locked');
        el.hidden = false;
        rail.hidden = false;
        if (!armed) {
          arm();
          armed = true;
        }
        ScrollTrigger.refresh();
        if (was !== undefined || savedIndex > 0) goto(savedIndex, false);
        ScrollTrigger.update();
      } else {
        if (was) savedIndex = app.store.get().section;
        el.hidden = true;
        rail.hidden = true;
        document.documentElement.classList.add('locked');
        window.scrollTo(0, 0);
      }
    },
  );

  app.commands.on('goto', (i) => goto(i, true));
  // Fonts and images settle after first layout; section offsets depend on them.
  void document.fonts.ready.then(() => armed && ScrollTrigger.refresh());

  return { el, rail, goto, start };
}
