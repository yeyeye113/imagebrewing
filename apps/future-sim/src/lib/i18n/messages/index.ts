// AUTO-GENERATED
import { zhCN } from './zh-CN.ts'
import { enUS } from './en-US.ts'
import { jaJP } from './ja-JP.ts'
import { koKR } from './ko-KR.ts'
import type { Locale } from '../types.ts'

export type MessageKey = keyof typeof zhCN

const messages: Record<Locale, Record<MessageKey, string>> = {
  'zh-CN': zhCN,
  'en-US': enUS,
  'ja-JP': jaJP,
  'ko-KR': koKR,
}

export function getMessage(locale: Locale, key: MessageKey): string {
  return messages[locale]?.[key] ?? messages['zh-CN'][key] ?? key
}

export { messages }
