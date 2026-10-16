document.documentElement.classList.add('js');

const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const progress = document.querySelector('.scroll-progress span');
const heroProduct = document.querySelector('.hero-product');
const ambientOne = document.querySelector('.ambient-one');
const ambientTwo = document.querySelector('.ambient-two');
const floatingTags = document.querySelectorAll('.floating-tag');
let scrollQueued = false;

function renderScroll() {
  const top = scrollY;
  const total = Math.max(1, document.documentElement.scrollHeight - innerHeight);
  progress.style.transform = `scaleX(${Math.min(1, top / total)})`;
  if (!reducedMotion && top < 1250) {
    const travel = Math.min(1, top / 1100);
    heroProduct.style.transform = `translate3d(0, ${travel * 54}px, 0) scale(${1 - travel * .035})`;
    floatingTags[0].style.transform = `translate3d(0, ${top * -.045}px, 0)`;
    floatingTags[1].style.transform = `translate3d(0, ${top * .035}px, 0)`;
  }
  if (!reducedMotion) {
    ambientOne.style.transform = `translate3d(0, ${top * .04}px, 0)`;
    ambientTwo.style.transform = `translate3d(0, ${top * -.025}px, 0)`;
  }
  scrollQueued = false;
}

addEventListener('scroll', () => {
  if (!scrollQueued) requestAnimationFrame(renderScroll);
  scrollQueued = true;
}, {passive: true});
renderScroll();

const revealObserver = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('revealed');
      revealObserver.unobserve(entry.target);
    }
  });
}, {threshold: .12, rootMargin: '0px 0px -8%'});
document.querySelectorAll('[data-reveal]').forEach(item => revealObserver.observe(item));

const sceneDetails = {
  network: ['AV DEVICES', '01 / 04', 'Find, copy, and confirm technical addresses.'],
  iptv: ['IPTV CHANNELS', '02 / 04', 'Keep every stream endpoint ready to test.'],
  inventory: ['EQUIPMENT INVENTORY', '03 / 04', 'Review stock by location and resolve missing information.'],
  backups: ['AV BACKUPS', '04 / 04', 'Keep known-good recovery files ready.']
};
const chapters = [...document.querySelectorAll('.story-chapter')];
const scenes = [...document.querySelectorAll('[data-product-scene]')];
const stageTitle = document.querySelector('#stage-title');
const stageIndex = document.querySelector('#stage-index');
const stageCaption = document.querySelector('#stage-caption');

function activateScene(name) {
  chapters.forEach(chapter => chapter.classList.toggle('active', chapter.dataset.scene === name));
  scenes.forEach(scene => {
    const active = scene.dataset.productScene === name;
    scene.classList.toggle('active', active);
    scene.setAttribute('aria-hidden', String(!active));
  });
  const [title, index, caption] = sceneDetails[name];
  stageTitle.textContent = title;
  stageIndex.textContent = index;
  stageCaption.textContent = caption;
}

const chapterObserver = new IntersectionObserver(entries => {
  const visible = entries.filter(entry => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
  if (visible) activateScene(visible.target.dataset.scene);
}, {threshold: [.25, .45, .65], rootMargin: '-28% 0px -38%'});
chapters.forEach(chapter => chapterObserver.observe(chapter));

if (!reducedMotion) {
  const stage = document.querySelector('.stage-frame');
  stage.addEventListener('pointermove', event => {
    if (innerWidth < 900) return;
    const box = stage.getBoundingClientRect();
    const x = (event.clientX - box.left) / box.width - .5;
    const y = (event.clientY - box.top) / box.height - .5;
    stage.style.transform = `perspective(1100px) rotateY(${x * 1.4}deg) rotateX(${y * -1.4}deg)`;
  });
  stage.addEventListener('pointerleave', () => { stage.style.transform = ''; });
}
