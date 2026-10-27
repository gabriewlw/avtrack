document.documentElement.classList.add('js');

const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const progress = document.querySelector('.scroll-progress span');
const heroProduct = document.querySelector('.hero-product');
const floatingTags = document.querySelectorAll('.floating-tag');
let scrollQueued = false;
let scrollRange = 1;

function renderScroll() {
  const top = scrollY;
  progress.style.transform = `scaleX(${Math.max(0, Math.min(1, top / scrollRange))})`;
  if (!reducedMotion && top < 1250) {
    const travel = Math.min(1, top / 1100);
    heroProduct.style.transform = `translate3d(0, ${travel * 54}px, 0) scale(${1 - travel * .035})`;
    floatingTags[0].style.transform = `translate3d(0, ${top * -.045}px, 0)`;
    floatingTags[1].style.transform = `translate3d(0, ${top * .035}px, 0)`;
  }
  scrollQueued = false;
}

addEventListener('scroll', () => {
  if (!scrollQueued) requestAnimationFrame(renderScroll);
  scrollQueued = true;
}, {passive: true});
// Cache document geometry when it changes, rather than measuring it each scroll.
function updateScrollRange() {
  scrollRange = Math.max(1, document.documentElement.scrollHeight - innerHeight);
  if (!scrollQueued) requestAnimationFrame(renderScroll);
  scrollQueued = true;
}
addEventListener('resize', updateScrollRange, {passive: true});
new ResizeObserver(updateScrollRange).observe(document.querySelector('main'));
updateScrollRange();

const commandBody = document.querySelector('#command-body');
const commandOutput = document.querySelector('#command-output');
const commandForm = document.querySelector('#command-form');
const commandInput = document.querySelector('#command-input');
const commandPrompt = 'C:\\Users\\visitor\\avtrack>';
const commandHistory = [];
let commandHistoryIndex = -1;

const terminalCommands = {
  help: [
    {text: 'AVTRACK COMMANDS', tone: 'command-accent'},
    {text: 'status      Show workspace capabilities', command: 'status'},
    {text: 'demo        Explore AVTrack with sample data', command: 'demo'},
    {text: 'aboutme     Meet the technician behind AVTrack', command: 'aboutme'},
    {text: 'purpose     Why I created AVTrack', command: 'purpose'},
    {text: 'benefits    How AVTrack can help your team', command: 'benefits'},
    {text: 'github      View the source repository', command: 'github'},
    {text: 'clear       Clear this terminal', command: 'clear'},
    {text: 'Use ↑ and ↓ to revisit commands.', tone: 'command-dim'}
  ],
  aboutme: [
    {text: 'WHO I AM', tone: 'command-accent'},
    {text: 'I’m Gabriel Moura, a broadcast technician working on cruise ships.'},
    {text: 'I look after onboard TV, satellite reception, and live production.'}
  ],
  purpose: [
    {text: 'WHY I CREATED AVTRACK', tone: 'command-accent'},
    {text: 'I wanted less time searching through scattered sheets during a busy shift.'},
    {text: 'So I built a local workspace to keep the technical details close at hand.'}
  ],
  benefits: [
    {text: 'HOW IT CAN HELP YOU', tone: 'command-accent'},
    {text: 'Find device IPs, open IPTV streams in one click, check spare equipment,'},
    {text: 'and keep configuration backups ready. Export what you need in seconds.'}
  ],
  status: [
    {text: 'AVTRACK WORKSPACE', tone: 'command-accent'},
    {text: '  Devices   READY   · IP addresses, VLANs and confirmation'},
    {text: '  IPTV         READY   · Channel endpoints, ports and sources'},
    {text: '  Inventory    READY   · Excel import, locations and stock checks'},
    {text: '  Backups   READY   · Local configuration recovery files'},
    {text: 'Runtime: local Python + SQLite · designed to work offline', tone: 'command-dim'}
  ],
  demo: [
    {text: 'EXHIBITION DEMO', tone: 'command-accent'},
    {text: 'Explore the interface with fictional devices, channels and inventory.'},
    {text: 'Launch the interactive demo →', href: '/demo'}
  ],
  about: [{text: 'Use aboutme to meet Gabriel, the technician behind AVTrack.', command: 'aboutme'}],
  github: [
    {text: 'SOURCE REPOSITORY', tone: 'command-accent'},
    {text: 'github.com/gabriewlw/avtrack ↗', href: 'https://github.com/gabriewlw/avtrack', external: true}
  ]
};

function appendTerminalLine(line) {
  const paragraph = document.createElement('p');
  if (line.tone) paragraph.className = line.tone;
  if (line.command) {
    paragraph.className = `${paragraph.className} command-option`.trim();
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.command = line.command;
    button.textContent = line.text;
    paragraph.append(button);
  } else if (line.href) {
    const link = document.createElement('a');
    link.href = line.href;
    link.textContent = line.text;
    if (line.external) {
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
    }
    paragraph.append(link);
  } else {
    paragraph.textContent = line.text;
  }
  commandOutput.append(paragraph);
  return paragraph;
}

function runTerminalCommand(value) {
  if (commandForm.hidden) return;
  const entered = value.trim();
  if (!entered) return;
  commandHistory.unshift(entered);
  commandHistoryIndex = -1;
  const normalized = entered.toLowerCase().replace(/^avtrack\s+/, '').replace(/^--/, '');
  if (normalized === 'clear' || normalized === 'cls') {
    commandOutput.replaceChildren();
  } else {
    const echo = document.createElement('p');
    const prompt = document.createElement('span');
    prompt.className = 'command-prompt';
    prompt.textContent = commandPrompt;
    echo.append(prompt, document.createTextNode(` ${entered}`));
    commandOutput.append(echo);
    const response = terminalCommands[normalized];
    if (response) response.forEach(appendTerminalLine);
    else appendTerminalLine({text: `'${entered}' is not an AVTrack command. Type 'help' to see the list.`, tone: 'command-dim'});
    appendTerminalLine({text: ''});
  }
  commandInput.value = '';
  commandBody.scrollTop = commandBody.scrollHeight;
}

commandForm.addEventListener('submit', event => {
  event.preventDefault();
  runTerminalCommand(commandInput.value);
});
commandInput.addEventListener('keydown', event => {
  if (event.ctrlKey && event.key.toLowerCase() === 'l') {
    event.preventDefault();
    runTerminalCommand('clear');
    return;
  }
  if (!['ArrowUp', 'ArrowDown'].includes(event.key) || !commandHistory.length) return;
  event.preventDefault();
  if (event.key === 'ArrowUp') commandHistoryIndex = Math.min(commandHistory.length - 1, commandHistoryIndex + 1);
  else commandHistoryIndex = Math.max(-1, commandHistoryIndex - 1);
  commandInput.value = commandHistoryIndex < 0 ? '' : commandHistory[commandHistoryIndex];
  requestAnimationFrame(() => commandInput.setSelectionRange(commandInput.value.length, commandInput.value.length));
});
commandBody.addEventListener('click', event => {
  const shortcut = event.target.closest('[data-command]');
  if (shortcut) {
    runTerminalCommand(shortcut.dataset.command);
    commandInput.focus();
    return;
  }
  if (!event.target.closest('a,input,button')) commandInput.focus();
});
// Play once when the terminal is visible. Keep page scrolling under the visitor’s control.
commandOutput.replaceChildren();
commandForm.hidden = true;
commandInput.disabled = true;
commandOutput.setAttribute('aria-busy', 'true');
const typingCursor = document.createElement('span');
typingCursor.className = 'command-cursor';
typingCursor.setAttribute('aria-hidden', 'true');
let followTerminal = true;
commandBody.addEventListener('scroll', () => {
  followTerminal = commandBody.scrollHeight - commandBody.scrollTop - commandBody.clientHeight < 48;
}, {passive: true});

function followTyping() {
  if (followTerminal) commandBody.scrollTop = commandBody.scrollHeight;
}
const terminalPause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function typeTerminalLine(line) {
  const paragraph = appendTerminalLine({...line, text: ''});
  const target = paragraph.firstElementChild || paragraph;
  const text = document.createTextNode('');
  target.append(text, typingCursor);
  if (reducedMotion) {
    text.data = line.text;
  } else {
    for (const character of line.text) {
      if (document.hidden) await new Promise(resolve => {
        const resume = () => {
          if (!document.hidden) {
            document.removeEventListener('visibilitychange', resume);
            resolve();
          }
        };
        document.addEventListener('visibilitychange', resume);
      });
      text.data += character;
      followTyping();
      await terminalPause(/[.,!?]/.test(character) ? 200 : 45 + Math.random() * 40);
    }
  }
  typingCursor.remove();
  followTyping();
}

async function playTerminalIntroduction() {
  for (const name of ['aboutme', 'purpose', 'benefits']) {
    for (const line of terminalCommands[name]) await typeTerminalLine(line);
    appendTerminalLine({text: '', tone: 'command-blank'});
    if (!reducedMotion) await terminalPause(850);
  }
  await typeTerminalLine({text: 'YOUR TURN — TRY A COMMAND', tone: 'command-accent'});
  await typeTerminalLine({text: 'Click a suggestion or type below. Try help to see every command.', tone: 'command-dim'});
  [
    {text: 'status → Inspect the workspace', command: 'status'},
    {text: 'demo → Explore sample data', command: 'demo'},
    {text: 'github → See the project', command: 'github'},
    {text: 'help → More commands', command: 'help'}
  ].forEach(appendTerminalLine);
  commandOutput.setAttribute('aria-busy', 'false');
  commandForm.hidden = false;
  commandInput.disabled = false;
  commandBody.dataset.introComplete = 'true';
  followTyping();
}

const terminalObserver = new IntersectionObserver(entries => {
  if (!entries.some(entry => entry.isIntersecting)) return;
  terminalObserver.disconnect();
  playTerminalIntroduction();
}, {threshold: .25});
terminalObserver.observe(commandBody);

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
  network: ['DEVICES', '01 / 04', 'Find, copy, and confirm technical addresses.'],
  iptv: ['IPTV CHANNELS', '02 / 04', 'Keep every stream endpoint ready to test.'],
  inventory: ['EQUIPMENT INVENTORY', '03 / 04', 'Review stock by location and resolve missing information.'],
  backups: ['BACKUPS', '04 / 04', 'Keep known-good recovery files ready.']
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
