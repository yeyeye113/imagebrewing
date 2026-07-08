// AUTO-GENERATED
import type { Locale } from './types.ts'

export interface OnboardingStep {
  step: number
  total: number
  title: string
  body: string
  nextPath?: string
  nextLabel?: string
}

const PATHS = ['/profile','/scores','/config','/run','/dashboard','/report'] as const
const NEXT: Record<string, string | undefined> = {
  '/profile': '/scores',
  '/scores': '/config',
  '/config': '/run',
  '/run': '/dashboard',
}

const DATA: Record<Locale, Record<string, Omit<OnboardingStep, 'step' | 'total' | 'nextPath'>>> = {
  "zh-CN": {
    "/profile": {
      "title": "先告诉引擎：你在做什么",
      "body": "填写作品名称、目标用户和核心功能。信息越具体，诊断越准——不必追求完美，后面还能改。",
      "nextLabel": "下一步：变量评分"
    },
    "/scores": {
      "title": "诚实给变量打分",
      "body": "按真实水平滑动评分，不要「自我感觉良好」。痛点、留存、分发是三项最敏感的杠杆。",
      "nextLabel": "下一步：模拟配置"
    },
    "/config": {
      "title": "选择模拟强度",
      "body": "快速模式适合试探方向；标准/深度模式样本更多、结论更稳。时间紧可先快速，定稿前再加深。",
      "nextLabel": "下一步：运行模拟"
    },
    "/run": {
      "title": "一键跑蒙特卡洛",
      "body": "点击「开始模拟」，全程在浏览器本地计算，数据不会上传。跑完会给出死亡概率与产品诊断。",
      "nextLabel": "跑完后看仪表盘"
    },
    "/dashboard": {
      "title": "读懂结论，再行动",
      "body": "顶部横幅是总判断；往下有死亡原因、改进方案和路线图。可导出完整报告分享给团队。"
    },
    "/report": {
      "title": "报告可分享、可导出",
      "body": "支持复制 Markdown、下载 .md 或导出 JSON。把诊断结论带回你的产品迭代会议。"
    }
  },
  "en-US": {
    "/profile": {
      "title": "Tell the engine what you're building",
      "body": "Name, users, and core features. More detail helps — you can edit later.",
      "nextLabel": "Next: Scores"
    },
    "/scores": {
      "title": "Score variables honestly",
      "body": "Slide to real levels, not wishful thinking. Pain, retention, distribution matter most.",
      "nextLabel": "Next: Config"
    },
    "/config": {
      "title": "Choose simulation intensity",
      "body": "Quick to probe; standard/deep for stable conclusions.",
      "nextLabel": "Next: Run"
    },
    "/run": {
      "title": "Run Monte Carlo",
      "body": "Runs locally in your browser. No upload. Get death odds and diagnosis.",
      "nextLabel": "Then view dashboard"
    },
    "/dashboard": {
      "title": "Read conclusions, then act",
      "body": "Banner is the verdict; below are causes, fixes, roadmap. Export to share."
    },
    "/report": {
      "title": "Shareable report",
      "body": "Copy Markdown, download .md, or export JSON for your team."
    }
  },
  "ja-JP": {
    "/profile": {
      "title": "まず何を作るか伝える",
      "body": "名前・ユーザー・機能を入力。詳細ほど精度向上。",
      "nextLabel": "次：変数スコア"
    },
    "/scores": {
      "title": "正直にスコアを付ける",
      "body": "現実的に評価。ペイン・リテンション・配信が重要。",
      "nextLabel": "次：設定"
    },
    "/config": {
      "title": "シミュレーション強度を選ぶ",
      "body": "クイックで試し、標準/ディープで安定判断。",
      "nextLabel": "次：実行"
    },
    "/run": {
      "title": "モンテカルロ実行",
      "body": "ブラウザ内でローカル実行。アップロードなし。",
      "nextLabel": "後でダッシュボードへ"
    },
    "/dashboard": {
      "title": "結論を読んで行動",
      "body": "バナーが総合判断。原因・改善・ロードマップあり。"
    },
    "/report": {
      "title": "共有可能なレポート",
      "body": "Markdownコピー・.md・JSONエクスポート。"
    }
  },
  "ko-KR": {
    "/profile": {
      "title": "엔진에 무엇을 만드는지 알려주세요",
      "body": "이름, 사용자, 핵심 기능을 입력하세요. 자세할수록 정확합니다.",
      "nextLabel": "다음: 변수 점수"
    },
    "/scores": {
      "title": "변수를 솔직하게 점수화",
      "body": "현실 수준으로 평가하세요. 페인·리텐션·유통이 핵심입니다.",
      "nextLabel": "다음: 설정"
    },
    "/config": {
      "title": "시뮬레이션 강도 선택",
      "body": "빠른 모드로 탐색, 표준/심층으로 안정적 결론.",
      "nextLabel": "다음: 실행"
    },
    "/run": {
      "title": "몬테카를로 실행",
      "body": "브라우저에서 로컬 실행. 업로드 없음.",
      "nextLabel": "완료 후 대시보드"
    },
    "/dashboard": {
      "title": "결론을 읽고 행동",
      "body": "배너가 총판단. 원인·개선·로드맵 확인.보내기 가능."
    },
    "/report": {
      "title": "공유 가능한 리포트",
      "body": "Markdown 복사, .md 다운로드, JSON보내기."
    }
  }
}

export function getOnboardingByPath(locale: Locale): Record<string, OnboardingStep> {
  const raw = DATA[locale] ?? DATA['zh-CN']
  const out: Record<string, OnboardingStep> = {}
  PATHS.forEach((path, i) => {
    const base = raw[path]
    if (!base) return
    out[path] = {
      step: Math.min(i + 1, 5),
      total: 5,
      title: base.title,
      body: base.body,
      nextPath: NEXT[path],
      nextLabel: base.nextLabel,
    }
  })
  return out
}
