/**
 * 张展nb666-Harness · 首次启动动画
 *
 * 第一次在一个项目里装上，播一段开机动画：把名字打出来，然后是那句话。
 * 播完在会话状态里留个记号，之后不再播。
 *
 * 原理：$.clock.every 定时推进帧，$.ui.invalidate('ui.render') 让引擎重画。
 * 画在 AbovePrompt 那条带子上——就在输入框上面，不挡任何东西。
 */
import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

/** 记号：这个会话播过了没 */
const 播过 = atom({ plugin: 'harness', key: '欢迎已播' } as const, false)
/** 当前帧。-1 = 没在播。 */
const 帧 = atom({ plugin: 'harness', key: '欢迎帧' } as const, -1)

/** 名字用字符画拼出来，一行行从中间撑开 */
const 名字 = [
  '  ███████╗██╗  ██╗ █████╗ ███╗   ██╗ ██████╗ ',
  '  ╚══███╔╝██║  ██║██╔══██╗████╗  ██║██╔════╝ ',
  '    ███╔╝ ███████║███████║██╔██╗ ██║██║  ███╗',
  '   ███╔╝  ██╔══██║██╔══██║██║╚██╗██║██║   ██║',
  '  ███████╗██║  ██║██║  ██║██║ ╚████║╚██████╔╝',
  '  ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ ',
]

/** 逐字打出来的问候 */
const 问候 = '很高兴在这里认识你，我会一直陪伴你。'

/** 转圈用的字符 */
const 转 = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

/** 名字有几帧（每行两帧：先亮后定位） */
const 名字帧数 = 名字.length * 2

export const register: Register = on => {
  // 会话开始：没播过就开播
  on('session.start', async ($, e, next) => {
    // -p 那种没人的场合不播，省得往日志里灌字符画
    if (!e.isInteractive) return next(e)
    if (await read($, 播过).catch(() => false)) return next(e)

    await update($, 帧, () => 0)

    let 现在 = 0
    const 总帧 = 名字帧数 + 问候.length + 24

    const 钟 = $.clock.every(65, async () => {
      现在 += 1
      await update($, 帧, () => 现在)
      $.ui.invalidate('ui.render')
      if (现在 >= 总帧) {
        钟.cancel()
        await update($, 帧, () => -1)
        await update($, 播过, () => true)
        $.ui.invalidate('ui.render')
      }
    })

    return next(e)
  })

  // 画那条带子。别的插件也可能画同一条，用 next 串起来。
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const 原始 = await read($, 帧).catch(() => -1)
    const 现在 = 原始 ?? -1
    if (现在 < 0) return next(e)

    const { Box, Text } = $.ui.resolve(e)

    // 第一阶段：名字一行行浮现
    const 名字帧 = Math.min(现在, 名字帧数)
    const 已出 = Math.ceil(名字帧 / 2)
    const 高亮 = 名字帧 % 2 === 1 && 已出 > 0 ? 已出 - 1 : -1

    // 第二阶段：逐字打问候
    const 问候帧 = Math.max(0, 现在 - 名字帧数)
    const 打出 = 问候.slice(0, 问候帧)
    const 还在名字 = 问候帧 === 0
    const 圈 = 转[现在 % 转.length] ?? '⠋'
    const 打完 = 现在 > 名字帧数 + 问候.length

    return (
      <Box key="harness-欢迎" flexDirection="column">
        {名字.slice(0, 已出).map((行, i) => (
          <Text key={`n${i}`} color={i === 高亮 ? 'cyanBright' : 'cyan'} bold>
            {行}
          </Text>
        ))}
        {已出 > 0 && <Text>{' '}</Text>}
        {还在名字 ? (
          <Text color="magentaBright">{`  ${圈} 张展nb666-Harness 正在启动…`}</Text>
        ) : (
          <Text color="magentaBright" bold>
            {`  ${打出}`}
            {!打完 && <Text dimColor>{'▌'}</Text>}
          </Text>
        )}
        {打完 && <Text dimColor>{'  ─────────────────────────────────────────────'}</Text>}
      </Box>
    )
  })
}
