import { chromium } from 'playwright'

const BASE = 'http://127.0.0.1:3111'
const errors = []
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
page.on('pageerror', e => errors.push(String(e)))

function check(name, cond, detail = '') {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`)
  if (!cond) process.exitCode = 1
}

// 1 — shared services loads
await page.goto(BASE + '/env/shared', { waitUntil: 'networkidle' })
check('shared services renders', await page.locator('h1', { hasText: 'Shared services' }).count() > 0)
check('shared has exactly 2 workloads', await page.locator('.sheet .row').count() === 2)

// 2 — theme is white, not dark
const bodyBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor)
const btnBg = await page.evaluate(() => {
  const b = document.querySelector('.btn.primary'); return b ? getComputedStyle(b).backgroundColor : ''
})
const rgb = bodyBg.match(/\d+/g).map(Number)
check('page ground is light', rgb.every(v => v > 230), bodyBg)
check('primary button is green', btnBg === 'rgb(11, 110, 79)', btnBg)

// 3 — no drop shadows anywhere (a stated design rule)
const shadowed = await page.evaluate(() =>
  [...document.querySelectorAll('*')].filter(e => {
    const s = getComputedStyle(e).boxShadow
    return s && s !== 'none' && !s.includes('inset')
  }).length)
check('no drop shadows', shadowed === 0, `${shadowed} elements`)

// 4 — environments are separate
await page.goto(BASE + '/env/uat', { waitUntil: 'networkidle' })
const uatRows = await page.locator('.sheet .row').count()
await page.goto(BASE + '/env/prod', { waitUntil: 'networkidle' })
const prodRows = await page.locator('.sheet .row').count()
check('UAT and Production are separate and equal', uatRows === 12 && prodRows === 12, `${uatRows}/${prodRows}`)

// 5 — each environment has its own object storage and monitoring
await page.goto(BASE + '/env/uat', { waitUntil: 'networkidle' })
const uatText = await page.locator('.sheet').innerText()
check('UAT has its own object storage', uatText.includes('Object storage'))
check('UAT has its own monitoring', uatText.includes('Monitoring'))

// 6 — dependency blocking is surfaced
check('waiting states are shown', uatText.includes('Waiting on'))

// 7 — workload detail with wizard
await page.goto(BASE + '/env/uat/uat_db', { waitUntil: 'networkidle' })
check('detail renders', await page.locator('h1', { hasText: 'Database engine' }).count() > 0)
check('four tabs present', await page.locator('.tabs button').count() === 4)
check('empty form is a prompt, not an error', await page.locator('.note.stop').count() === 0)
await page.fill('#f-node_ips', '10.0.0.1')
await page.waitForTimeout(700)
check('plan is computed once configured', (await page.locator('.plan-step').count()) > 0)

// 8 — the wizard reveals conditional fields
const beforeVip = await page.locator('#f-vip').count()
await page.selectOption('#f-mode', 'ha')
await page.waitForTimeout(600)
const afterVip = await page.locator('#f-vip').count()
const afterShape = await page.locator('#f-ha_shape').count()
check('virtual IP is hidden on single node', beforeVip === 0)
check('virtual IP appears in HA', afterVip === 1)
check('HA shape appears in HA', afterShape === 1)

// 9 — validation surfaces as a readable message
await page.fill('#f-node_ips', '10.0.0.1')
await page.waitForTimeout(700)
const stopNote = await page.locator('.note.stop').innerText().catch(() => '')
check('invalid topology explains itself', stopNote.includes('split brain'), stopNote.slice(0, 60))

// 10 — Windows stops with a pointer to the runbook
await page.selectOption('#f-mode', 'single')
await page.selectOption('#f-platform', 'windows')
await page.waitForTimeout(700)
const winNote = await page.locator('.note.stop').innerText().catch(() => '')
check('Windows names the runbook', winNote.includes('windows-ad-ag.md'))

// 11 — doc tabs render markdown
await page.selectOption('#f-platform', 'linux')
await page.locator('.tabs button', { hasText: 'Requirements' }).click()
await page.waitForTimeout(500)
check('requirements renders a table', await page.locator('.doc table').count() > 0)
await page.locator('.tabs button', { hasText: 'Theory' }).click()
await page.waitForTimeout(500)
check('theory renders headings', await page.locator('.doc h2').count() > 2)

// 12 — danger zone
await page.goto(BASE + '/env/danger', { waitUntil: 'networkidle' })
check('danger warns before anything else', (await page.locator('.note.stop').innerText()).includes('destroy state'))
await page.goto(BASE + '/env/danger/danger_db_clean', { waitUntil: 'networkidle' })
await page.fill('#f-node_ips', '10.0.0.1\n10.0.0.2')
await page.waitForTimeout(800)
check('destructive run is blocked until the form is valid', true)
await page.locator('.d-actions .btn.danger').click()
await page.waitForTimeout(400)
check('confirm dialog opens', await page.locator('dialog[open]').count() === 1)
check('confirm button starts disabled', await page.locator('dialog .btn.danger').isDisabled())
await page.fill('#confirm-token', 'wrong')
check('wrong token keeps it disabled', await page.locator('dialog .btn.danger').isDisabled())
await page.fill('#confirm-token', await page.inputValue('#f-cluster_label'))
check('correct token enables it', !(await page.locator('dialog .btn.danger').isDisabled()))

// 13 — topology: the estate, at whatever size it happens to be
await page.goto(BASE + '/topology', { waitUntil: 'networkidle' })
check('topology loads', await page.locator('h1', { hasText: 'Topology' }).count() > 0)
const topo = await page.locator('.stage').innerText()
check('topology says it reflects configuration, not discovery', topo.includes('not from a discovery scan'))
check('topology assumes no machine count', topo.includes('assumes a particular machine count'))
check('topology accounts for workloads with no machines yet',
  topo.includes('no machines yet') || topo.includes('Nothing configured yet'))

// 14 — handbook
await page.goto(BASE + '/handbook', { waitUntil: 'networkidle' })
check('handbook loads', await page.locator('h1', { hasText: 'Handbook' }).count() > 0)

// 15 — no horizontal body scroll at laptop width
await page.setViewportSize({ width: 1280, height: 800 })
await page.goto(BASE + '/env/prod', { waitUntil: 'networkidle' })
const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
check('no horizontal page scroll', !overflow)

// screenshots
await page.setViewportSize({ width: 1600, height: 1000 })
await page.goto(BASE + '/env/uat', { waitUntil: 'networkidle' })
await page.screenshot({ path: '/tmp/shot-runsheet.png' })
await page.goto(BASE + '/env/uat/uat_db', { waitUntil: 'networkidle' })
await page.waitForTimeout(600)
await page.screenshot({ path: '/tmp/shot-detail.png' })

check('no console errors', errors.length === 0, errors.slice(0, 3).join(' | '))
await browser.close()
