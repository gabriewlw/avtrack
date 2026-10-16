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

const commandBody = document.querySelector('#command-body');
const commandOutput = document.querySelector('#command-output');
const commandForm = document.querySelector('#command-form');
const commandInput = document.querySelector('#command-input');
const commandPrompt = 'C:\\Users\\visitor\\broadcastgab>';
const commandHistory = [];
let commandHistoryIndex = -1;

const terminalCommands = {
  help: [
    {text: 'AVTRACK COMMANDS', tone: 'command-accent'},
    {text: '  status      Show workspace capabilities'},
    {text: '  devices     Open the AV device workspace'},
    {text: '  iptv        Open the IPTV channel workspace'},
    {text: '  inventory   Open equipment inventory'},
    {text: '  backups     Open the recovery-file archive'},
    {text: '  demo        Explore AVTrack with sample data'},
    {text: '  about       Read why AVTrack was built'},
    {text: '  github      View the source repository'},
    {text: '  clear       Clear this terminal'},
    {text: 'Use ↑ and ↓ to revisit commands.', tone: 'command-dim'}
  ],
  status: [
    {text: 'AVTRACK WORKSPACE', tone: 'command-accent'},
    {text: '  AV devices   READY   · IP addresses, VLANs and confirmation'},
    {text: '  IPTV         READY   · Channel endpoints, ports and sources'},
    {text: '  Inventory    READY   · Excel import, locations and stock checks'},
    {text: '  AV backups   READY   · Local configuration recovery files'},
    {text: 'Runtime: local Python + SQLite · designed to work offline', tone: 'command-dim'}
  ],
  devices: [
    {text: 'AV DEVICES', tone: 'command-accent'},
    {text: 'Search equipment by name, venue, system, IP address or VLAN.'},
    {text: 'Open AV Devices workspace →', href: '/#av'}
  ],
  iptv: [
    {text: 'IPTV CHANNELS', tone: 'command-accent'},
    {text: 'Track onboard and satellite streams with IP, UDP port and source.'},
    {text: 'Open IPTV workspace →', href: '/#iptv'}
  ],
  inventory: [
    {text: 'EQUIPMENT INVENTORY', tone: 'command-accent'},
    {text: 'Paste Excel tables, review missing data by location and confirm stock.'},
    {text: 'Open Inventory workspace →', href: '/inventory'}
  ],
  backups: [
    {text: 'AV BACKUPS', tone: 'command-accent'},
    {text: 'Keep known-good Videohub, ATEM, receiver and OBS files ready.'},
    {text: 'Open AV Backups workspace →', href: '/backups'}
  ],
  demo: [
    {text: 'EXHIBITION DEMO', tone: 'command-accent'},
    {text: 'Explore the interface with fictional devices, channels and inventory.'},
    {text: 'Launch the interactive demo →', href: '/demo'}
  ],
  about: [
    {text: 'ABOUT AVTRACK', tone: 'command-accent'},
    {text: 'Created by a cruise ship broadcast technician to keep operational'},
    {text: 'addresses, channel endpoints, stock records and recovery files together.'}
  ],
  github: [
    {text: 'SOURCE REPOSITORY', tone: 'command-accent'},
    {text: 'github.com/gabriewlw/avtrack ↗', href: 'https://github.com/gabriewlw/avtrack', external: true}
  ]
};

function appendTerminalLine(line) {
  const paragraph = document.createElement('p');
  if (line.tone) paragraph.className = line.tone;
  if (line.href) {
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
}

function runTerminalCommand(value) {
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
  if (!event.target.closest('a,input,button')) commandInput.focus();
});
document.querySelectorAll('.command-chips [data-command]').forEach(button => {
  button.addEventListener('click', () => {
    runTerminalCommand(button.dataset.command);
    commandInput.focus();
  });
});

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
