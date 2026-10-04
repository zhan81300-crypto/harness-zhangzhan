/**
 * 张展nb666-Harness · hooks 模块
 *
 * 治三个病：
 *   一、边做边改 —— 战略没确认就写产物，做到一半发现方向错
 *   二、凑形式验收 —— 用"全绿/X项通过/哈希一致"代替真打开用一遍
 *   三、前脚说完后脚忘 —— 用户上轮说的偏好，下轮就忘了
 *
 * 做法不是"在外面拦"，是改 AI 的思考层：
 *   prompt.compose  把规则写进 system prompt，让 AI 天生按这套走
 *   prompt.submit   用户每说一句话，当场把该记的塞给模型去记（用户看不见）
 *   tool.call       战略没确认时，物理拦住写产物（这道必须硬）
 *   turn.complete   这轮结束前，该记的没记就催一次
 *   session.start   有 harness 目录就把状态亮出来
 *   /harness        看当前到哪一步；/审查 派一个干净 LLM 做对抗性审查
 *
 * 换 LLM 也不怕：规则本身是纯文本（adapters/规则-通用.md），
 * 这份 hooks 只是 Claude Code 上的适配器。别的工具照着那份文本做就行。
 */
import type { Register } from 'claude-code'

// ---------------------------------------------------------------- 常量

/** 用户说这些，就认为要开 harness */
const 关键词 = ['用我的harness', '开harness', '展的harness', '张展nb666']

/** 信号词 */
const 偏好信号 = ['偏好', '以后', '永远', '任何时候', '记住', '放进记忆', '跨对话',
  '我不喜欢', '我喜欢', '别再', '不要再', '我讨厌']
const 纠正信号 = ['错了', '不对', '跑偏', '你没', '你怎么', '重做', '推翻', '我说过',
  '不是这个', '又忘', '说人话', '别啰嗦', '我不是这个意思']
const 要求信号 = ['必须', '禁止', '不许', '不能', '应该', '要做到', '改成', '加上',
  '去掉', '我要', '给我', '希望', '需要']

/** 写产物的工具 */
const 写工具集 = new Set(['Write', 'Edit', 'NotebookEdit', 'MultiEdit'])

/** Bash 里看起来在写盘的样子。挡得住常见的，挡不住全部——这是知情的取舍。 */
const 写盘样 = /(^|[;&|]\s*)(cat\s*>|tee\b|sed\s+-i|python[0-9.]*\s+-c|node\s+-e|perl\s+-i|>\s*[^\s|&;]+)/
function 像写盘(命令: string): boolean {
  return 写盘样.test(命令)
}

/** 战略闸拦下来时给模型看的说明 */
function 拦截说明(拦了什么: string): string {
  return (
    `[harness 战略闸] 战略还没经用户确认，现在不能写产物。\n` +
    `拦下的：${拦了什么}\n\n` +
    `先做完阶段一，再回来：\n` +
    `1. 穷尽调查——相关的东西真读一遍，不抽查、不猜\n` +
    `2. 列出全部问题——结合实际情况列全，不筛不删\n` +
    `3. 分主干与配套——谁依赖谁，先做哪个\n` +
    `4. 抽象宏观战略——在什么目标和原则下，为了做什么，用什么方法，做成什么样\n` +
    `5. 用复现思路写 \`${战略档}\`——每步写明影响范围、怎么算做到了\n` +
    `6. 拿给用户确认，点头之后把顶部改成「状态：已确认」\n\n` +
    `禁止为了让流程跑通而删变量、换问题、跳过难处理的地方。沉默不等于同意。`
  )
}

const 目录 = 'harness'
const 总纲档 = `${目录}/总纲.md`
const 战略档 = `${目录}/战略步骤.md`

/** 审查员的 system prompt —— 对抗性来自上下文隔离，不来自措辞 */
const 审查员系统提示 = [
  '你是独立审查员。你的上下文只有这一段和下面给你的那一份东西。',
  '你不知道前面有谁查过什么、过了几项，也别去猜——知道"前面都过了"就会放水。',
  '',
  '你只做一件事：针对给你的这一个具体问题，看这个成品到底成不成。',
  '',
  '规矩：',
  '1. 先真实用一遍的思路看。能看出界面/操作/输出的，就从使用者角度看它在实际场景里行不行，不是看结构齐不齐。',
  '2. 综合判断，不逐项打分。不列检查项、不算数量、不给分数、不摆判断过程。',
  '3. 找到疑点先自己解释（设计如此？别处已处理？场景不适用？）。解释得通就不是问题，解释不通才是真问题。不硬挑刺，也不放水。',
  '4. 不猜、不占位。拿不到的东西就说拿不到，别用"可能""大概"糊过去。',
  '',
  '结论只能是两种：做到了 / 没做到。',
  '禁止用这些词：全绿、全部通过、测试通过、验收通过、门禁、冻结、覆盖率、X项通过、打勾。',
  '检查项只能发现问题，不能定义完成。所有检查都没报错但成品不好用，结论就是没做到。',
  '',
  '输出格式：',
  '结论：做到了 / 没做到',
  '怎么看出来的：（一两句，就事论事）',
  '哪儿不行：',
  '- （问题）｜在哪儿｜为什么解释不通',
  '没问题就不写"哪儿不行"。不写套话，不写总结，不写建议清单。',
].join('\n')

/** 转圈用的字符 */
const 转圈 = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

/** 现在正在忙什么。空字符串=闲着。带子上就看这个。 */
let 现在在忙 = ''
/** 这个会话归档了几笔 */
let 记了几笔 = 0

// ---------------------------------------------------------------- 小工具

/** 从工具调用参数里取文件路径 */
function 取路径(e: Record<string, unknown>): string | null {
  for (const k of ['file_path', 'path', 'notebook_path', 'filePath']) {
    const v = e[k]
    if (typeof v === 'string' && v) return v
  }
  return null
}

/** 拼绝对路径并折叠 . 和 ..（不依赖 node） */
function 规整(p: string, cwd: string): string {
  const s = p.replace(/\\/g, '/')
  const 绝对 = s.startsWith('/') || /^[A-Za-z]:\//.test(s)
  const 全 = 绝对 ? s : `${cwd.replace(/\\/g, '/').replace(/\/$/, '')}/${s}`
  const 段: string[] = []
  for (const 一 of 全.split('/')) {
    if (一 === '' || 一 === '.') continue
    if (一 === '..') 段.pop()
    else 段.push(一)
  }
  return '/' + 段.join('/')
}

/** 子路径是否在父路径底下（按目录边界比，避免同名文件夹误判） */
function 在里面(子: string, 父: string): boolean {
  const s = 子.replace(/\/$/, '')
  const f = 父.replace(/\/$/, '')
  return s === f || s.startsWith(f + '/')
}

/** 收窄一段话 */
function 摘(话: string, 上限 = 120): string {
  const 净 = 话.replace(/\s+/g, ' ').trim()
  return 净.length <= 上限 ? 净 : 净.slice(0, 上限) + '…'
}

/** 认这句话里有什么要归档的 */
function 认信号(话: string) {
  return {
    偏好: 偏好信号.some(w => 话.includes(w)),
    纠正: 纠正信号.some(w => 话.includes(w)),
    要求: 要求信号.some(w => 话.includes(w)),
  }
}

// ---------------------------------------------------------------- 模块

export const register: Register = on => {
  // 会话级缓存。每次工具调用都读盘太慢，缓存住，写文件后刷新。
  let 缓存: { cwd: string; 有: boolean } | null = null
  let 战略已确认 = false


  /** 拿本会话里项目状态 */
  const 看状态 = async ($: Parameters<Parameters<Register>[0]> extends never ? never : any) => {
    if (!缓存) {
      const cwd: string = await $.session.cwd()
      const 有: boolean = await $.fs.exists(`${cwd}/${总纲档}`)
      缓存 = { cwd, 有 }
      if (有) {
        战略已确认 = await $.fs
          .read(`${cwd}/${战略档}`)
          .then((t: string) => /状态[:：]\s*已确认/.test(t))
          .catch(() => false)
      }
    }
    return { cwd: 缓存.cwd, 有: 缓存.有, 已确认: 战略已确认 }
  }

  /** 有东西变了，作废缓存 */
  const 作废 = () => { 战略已确认 = false; 缓存 = 缓存 ? { ...缓存 } : null }

  // ============================================ 一、改 system prompt
  // 这是"魔改"的核心：规则不是外部指令，是 AI 自己的一部分。
  on('prompt.compose', async ($, e, next) => {
    const 结果 = await next(e)
    const { 有, 已确认 } = await 看状态($)
    if (!有) return 结果

    const 规则 = [
      '# 本项目已启用 harness',
      '',
      '这不是建议，是你的工作方式。规则全文在 skill「harness」和 harness/ 目录里。',
      '',
      '## 说话方式',
      '只说能直接决定事情的话。说人话，不提脚本名、不提内部术语、不摆过程。',
      '汇报只有两种结论：**做到了 / 没做到**。',
      '',
      '## 战略闸（硬规矩）',
      已确认
        ? `战略已确认（${战略档} 顶部是「状态：已确认」），按里面的复现步骤走。`
        : `**${战略档} 还没确认。现在不许写任何产物文件**，只能写 ${目录}/ 目录自己的文档。`,
      '要改方向：把问题提到战略口径 → 跟用户确认 → 改 战略步骤.md → 记进 经验日记.md。',
      '不另起新计划、不新建文件。',
      '',
      '## 验收（硬规矩）',
      '真打开、真运行、真用一遍，站最终使用者角度判断。',
      '禁止说：全绿、全部通过、测试通过、X 项通过、覆盖率、门禁、冻结、哈希一致。',
      '检查项只能发现问题，**不能定义完成**。所有检查都过了但成品不好用，就是没做到。',
      '发现问题先自己解释（设计如此？别处已处理？场景不适用？），解释不通才是真问题。',
      '',
      '## 归档（硬规矩）',
      '用户每说一句有用的话，**当场归档，不等这轮结束**：',
      '· 要求 → `经验日记.md`：他想解决什么、我该怎么改。一两句，口语化',
      '· 偏好 → `用户偏好.md`：用他自己的说法，别改意思',
      '· 纠正 → `经验日记.md` 通病清单：我错在哪、根子上为什么错。只记新的',
      '· 流水 → `动作与交互.md`',
      '',
      '## 改动范围',
      '小改只查受影响部分；动核心数据或核心方法才全面重查。禁止小改就全盘重置。',
    ].join('\n')

    return {
      sections: [...结果.sections, { id: 'harness:rules', text: 规则, scope: 'session' as const }],
    }
  })

  // ============================================ 二、用户每说一句话
  // 先机械地把原话落进流水（这步死，漏不掉），
  // 再往模型眼前塞一条"现在就归档"的指令（用户看不见，不打断体验）。
  on('prompt.submit', async ($, e, next) => {
    const { cwd, 有 } = await 看状态($)
    if (!有) return next(e)

    const 话 = e.text ?? ''
    if (!话.trim()) return next(e)

    // 1. 原话按时间落进 动作与交互.md
    try {
      现在在忙 = '在记流水'
      const 档 = `${cwd}/${目录}/动作与交互.md`
      const 旧 = await $.fs.read(档).catch(() => '')
      const 时刻 = new Date(await $.clock.now()).toISOString().slice(5, 16).replace('T', ' ')
      await $.fs.write(档, 旧 + `\n- \`${时刻}\` 用户说：${摘(话).replace(/\n/g, ' ')}\n`)
      记了几笔 += 1
    } catch { /* 流水记不上不该拦住对话 */ } finally {
      现在在忙 = ''
    }

    // 2. 认出该归档的
    const { 偏好, 纠正, 要求 } = 认信号(话)
    const 类型 = [偏好 && '偏好', 纠正 && '纠正', 要求 && '要求'].filter(Boolean) as string[]
    if (!类型.length) return next(e)

    // 3. 给模型一条它看得见、用户看不见的指令
    const 指令 = [
      `[harness 实时归档] 用户这句话里有**${类型.join('和')}**，现在就归档，别等：`,
      `原话：${摘(话, 200)}`,
      '· 往 `harness/经验日记.md` 加一条：他这轮想干啥、要解决什么问题、我该怎么改。一两句，口语化，不抄原话。',
    ]
    if (偏好) 指令.push('· 这条带偏好，同时追加进 `harness/用户偏好.md`，用他自己的说法，别改意思。')
    if (纠正) 指令.push('· 这条是在纠我。把我错在哪、根子上为什么错，写进 `harness/经验日记.md` 的通病清单。只记新的。')
    指令.push('先在回复里把归档做掉（改 harness 目录里的文件），再干别的。')

    return next({ ...e, context: [...(e.context ?? []), 指令.join('\n')] })
  })

  // ============================================ 三、写产物前拦住
  // 这条必须是硬的。战略没确认就写产物，是第一个病。
  on('tool.call', async ($, e, next) => {
    const 是写工具 = 写工具集.has(e.tool)
    const 是Bash = e.tool === 'Bash'
    if (!是写工具 && !是Bash) return next(e)

    const { cwd, 有, 已确认 } = await 看状态($)
    if (!有 || 已确认) return next(e)

    const 项目根 = cwd.replace(/\\/g, '/')

    // Bash 是个绕过口：cat > 文件、tee、sed -i、python -c 都能写盘。
    // 只能靠命令模式认，认不全是必然的，这里挡住最常见的几种。
    if (是Bash) {
      const 命令 = String((e as unknown as Record<string, unknown>).command ?? '')
      if (!像写盘(命令)) return next(e)
      if (命令.includes(`${目录}/`) || 命令.includes(`${目录}\\`)) return next(e) // 写 harness 自己的文档，放行
      return { deny: 拦截说明(`（命令）${命令.slice(0, 200)}`) }
    }

    const 路径 = 取路径(e as unknown as Record<string, unknown>)
    if (!路径) return next(e)

    const 绝对 = 规整(路径, cwd)
    if (在里面(绝对, `${项目根}/${目录}`)) return next(e) // harness 自己的文档，放行
    if (!在里面(绝对, 项目根)) return next(e) // 不在这个项目里，不管

    return { deny: 拦截说明(`（文件）${路径}`) }
  })
  // ============================================ 四、这轮结束前查一遍
  on('turn.complete', async ($, e, next) => {
    // 子智能体自己的轮结束也会到这里，别把它的结束当成主对话的结束
    if (e.agentId !== undefined) return next(e)

    const { cwd, 有, 已确认 } = await 看状态($)
    if (!有) return next(e)

    try {
      const 流水 = await $.fs.read(`${cwd}/${目录}/动作与交互.md`).catch(() => '')
      const 日记 = await $.fs.read(`${cwd}/${目录}/经验日记.md`).catch(() => '')
      const 偏好档 = await $.fs.read(`${cwd}/${目录}/用户偏好.md`).catch(() => '')

      const 最近 = 认信号(流水.split('\n').slice(-6).join('\n'))
      if ((最近.偏好 || 最近.纠正 || 最近.要求) && 日记.length < 200 && 偏好档.length < 300) {
        $.ui.toast('harness：这轮有该归档的没记，去补 经验日记.md')
      }

      if (!已确认) {
        const 步骤 = await $.fs.read(`${cwd}/${战略档}`).catch(() => '')
        if (步骤.includes('（结合现状列全')) {
          $.ui.toast('harness：战略步骤还空着，先跟用户把战略定死再动手')
        }
      }
    } catch { /* 查不动就算了，不该因为查不动把对话卡住 */ }

    作废()
    return next(e)
  })

  // ============================================ 五、会话开始
  on('session.start', async ($, e, next) => {
    const { 有, 已确认 } = await 看状态($)
    if (有) $.ui.status(已确认 ? 'harness · 战略已确认' : 'harness · 战略待确认')

    // 注册斜杠命令。session.start 首次是被 await 的，第一轮就能用。
    await $.command.register({
      name: 'harness',
      description: '看 harness 到哪一步了',
    }).catch(() => {})
    await $.command.register({
      name: '审查',
      description: '派一个干净上下文的 LLM 做对抗性审查：/审查 <文件路径> <要问的问题>',
    }).catch(() => {})

    return next(e)
  })

  // ============================================ 六、斜杠命令的实现

  on('command.run', async ($, e, next) => {
    // ---- /harness：看状态
    if (e.command === 'harness') {
      const cwd = await $.session.cwd()
      const 有 = await $.fs.exists(`${cwd}/${总纲档}`)
      if (!有) {
        return {
          text:
            '这个项目还没铺 harness。\n\n' +
            '说你项目里还没铺 harness，走阶段一：穷尽调查 → 列全部问题 → 分主干配套 → ' +
            '抽象宏观战略 → 写复现步骤 → 跟你确认。\n\n' +
            '模板在插件的 skills/harness/模板/，整个复制成项目里的 harness/。',
        }
      }
      const 已确认 = await $.fs
        .read(`${cwd}/${战略档}`)
        .then((t: string) => /状态[:：]\s*已确认/.test(t))
        .catch(() => false)
      return {
        text:
          `harness 状态\n\n` +
          `战略：${已确认 ? '已确认，按复现步骤走' : '**待确认**——现在不能写产物'}\n\n` +
          (已确认 ? '继续照 战略步骤.md 走。' : '先做完阶段一，拿给用户确认。'),
      }
    }

    // ---- /审查：派一个干净 LLM 做对抗性审查
    // 上下文只有一个成品 + 一个问题。不继承会话历史、不继承 CLAUDE.md、不给工具。
    // 对抗性来自隔离，不来自措辞。
    if (e.command === '审查') {
      const 参数 = ((e.args ?? '') as string).trim()
      const 空 = 参数.indexOf(' ')
      if (空 < 0) {
        return { text: '用法：/审查 <文件路径> <要问的问题>\n例：/审查 src/a.ts 实际场景里能不能用' }
      }
      const 目标 = 参数.slice(0, 空)
      const 问题 = 参数.slice(空 + 1).trim()

      let 成品: string
      try {
        成品 = await $.fs.read(目标)
      } catch {
        return { text: `读不到 ${目标}，检查路径。` }
      }

      const 上限 = 60_000
      const 截断 = 成品.length > 上限
      const 正文 = 截断 ? 成品.slice(0, 上限) : 成品

      const 会话模型 = await $.session.model()
      const 答 = await $.model
        .complete({
          model: 会话模型,
          system: 审查员系统提示,
          prompt:
            `<成品 path="${目标}">\n${正文}\n</成品>\n` +
            (截断 ? `（太长，只给了前 ${上限} 字）\n` : '') +
            `\n问题：${问题}`,
          maxTokens: 2048,
          effort: 'high',
          timeoutMs: 120_000,
        })
        .catch((err: unknown) => ({ isAnswered: false as const, reason: 'api-error' as const, error: String(err) }))

      if (!答.isAnswered) {
        return { text: `审查没跑起来：${'reason' in 答 ? 答.reason : '未知'}` }
      }
      return { text: String(答.text) }
    }

    return next(e)
  })

  // ============================================ 七、实时显示它在干活
  // 就是输入框上面那条带子。这不只是装饰——它让"系统真的在盯着"这件事看得见。
  // 状态：战略待确认 / 正在归档 / 正在守住 / 躺着不动
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const { 有, 已确认 } = await 看状态($)
    if (!有) return next(e)

    const { Box, Text } = $.ui.resolve(e)
    const 圈 = 转圈[(await $.clock.now() / 120 | 0) % 转圈.length] ?? '⠋'

    const 线 = 现在在忙
      ? { 符: 圈, 色: 'yellowBright', 字: 现在在忙 }
      : 已确认
        ? { 符: '◆', 色: 'greenBright', 字: '战略已确认' }
        : { 符: '◇', 色: 'redBright', 字: '战略待确认 · 不能写产物' }

    return (
      <Box key="harness-带" justifyContent="flex-start">
        <Text color={线.色}>{`${线.符} `}</Text>
        <Text color={线.色} bold>
          {'张展nb666 · '}
        </Text>
        <Text dimColor>{线.字}</Text>
        <Text dimColor>{`   记 ${记了几笔} 笔`}</Text>
      </Box>
    )
  })
}
