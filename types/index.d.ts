declare module 'claude-code' {
  interface PluginState {
    'harness': {
      /** 这个会话里，项目有没有 harness 目录 */
      有目录?: boolean
      /** 战略步骤确认了没（缓存，写文件后作废） */
      战略已确认?: boolean
      /** 首次启动动画播过了没 */
      欢迎已播?: boolean
      /** 启动动画当前帧，-1 表示没在播 */
      欢迎帧?: number
      /** 这个会话归档了几笔 */
      记了几笔?: number
      /** 现在正在忙什么（空=闲着） */
      现在在忙?: string
    }
  }
}
