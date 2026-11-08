/**
 * Conversation Insight — an alternate conversation view for DSH.
 *
 * Registers a new tab in the Conversation header (beside Chat, Trajectory and
 * Stats) that renders a compact, real-time summary of the current session:
 * turn/step counts, message and tool-call counts, timing and status.
 */

const NS = 'conv-insight';

const en = {
  'view.insight': 'Insight',
  'title': 'Conversation insight',
  'status.running': 'Running',
  'status.idle': 'Idle',
  'status.blank': 'Waiting for the first message',
  'metrics.turns': 'Turns',
  'metrics.steps': 'Steps',
  'metrics.messages': 'Messages',
  'metrics.user': 'User',
  'metrics.assistant': 'Assistant',
  'metrics.tools': 'Tools',
  'metrics.commands': 'Commands',
  'metrics.errors': 'Errors',
  'metrics.duration': 'Duration',
  'metrics.notAvailable': '—',
  'unit.seconds': '{value}s',
  'empty.title': 'No conversation loaded',
  'empty.body': 'Select a session to see its live summary.',
};

const zh = {
  'view.insight': '洞察',
  'title': '会话洞察',
  'status.running': '运行中',
  'status.idle': '空闲',
  'status.blank': '等待第一条消息',
  'metrics.turns': '轮次',
  'metrics.steps': '步骤',
  'metrics.messages': '消息',
  'metrics.user': '用户',
  'metrics.assistant': '助手',
  'metrics.tools': '工具',
  'metrics.commands': '命令',
  'metrics.errors': '错误',
  'metrics.duration': '时长',
  'metrics.notAvailable': '—',
  'unit.seconds': '{value} 秒',
  'empty.title': '未加载会话',
  'empty.body': '选择一个会话以查看实时摘要。',
};

window.__ModuleLoader__.load({
  id: '@local/conversation-insight',
  factory(require) {
    const React = require('react');
    const h = React.createElement;

    /**
     * Format a duration in milliseconds into a compact, localized string.
     * @param {number} ms
     * @param {(key: string, values?: Record<string, unknown>) => string} t
     */
    function formatDuration(ms, t) {
      if (!Number.isFinite(ms) || ms < 0) return t('metrics.notAvailable');
      const seconds = Math.round(ms / 1000);
      if (seconds < 60) return t('unit.seconds', { value: seconds });
      const minutes = Math.floor(seconds / 60);
      const rem = seconds % 60;
      return `${minutes}:${String(rem).padStart(2, '0')}`;
    }

    /**
     * Derive a stable insight object from the current Chat snapshot.
     * @param {import('@deepseek-ai/dsh-client-ui-chat/client').ChatSnapshot | undefined} chat
     * @param {import('@deepseek-ai/dsh-api-session-controller/client').SessionSnapshot | undefined} session
     * @returns {{
     *   turnCount: number;
     *   stepCount: number;
     *   userCount: number;
     *   assistantCount: number;
     *   toolCount: number;
     *   commandCount: number;
     *   errorCount: number;
     *   durationMs: number;
     *   isRunning: boolean;
     * }}
     */
    function deriveInsight(chat, session) {
      const empty = {
        turnCount: 0,
        stepCount: 0,
        userCount: 0,
        assistantCount: 0,
        toolCount: 0,
        commandCount: 0,
        errorCount: 0,
        durationMs: 0,
        isRunning: session?.running === true,
      };
      if (chat == null) return empty;

      const nodes = chat.nodes?.values?.() ?? [];
      let userCount = 0;
      let assistantCount = 0;
      let toolCount = 0;
      let commandCount = 0;
      let errorCount = 0;

      for (const node of nodes) {
        switch (node.kind) {
          case 'user':
            userCount += 1;
            break;
          case 'assistant-step':
            assistantCount += 1;
            break;
          case 'tool-call':
            toolCount += 1;
            break;
          case 'command':
          case 'command-input':
            commandCount += 1;
            break;
          case 'turn-error':
          case 'model-retry':
            errorCount += 1;
            break;
          default:
            break;
        }
      }

      const turnOrder = chat.timeline?.turnOrder ?? [];
      let stepCount = 0;
      for (const turn of turnOrder) {
        const turnLoc = chat.timeline?.turns?.get?.(turn);
        if (turnLoc?.steps) stepCount += turnLoc.steps.length;
      }

      let durationMs = 0;
      if (turnOrder.length > 0) {
        const firstTurn = chat.timeline?.turns?.get?.(turnOrder[0]);
        const lastTurn = chat.timeline?.turns?.get?.(turnOrder[turnOrder.length - 1]);
        const start = firstTurn?.start?.time;
        const end = lastTurn?.end?.time ?? lastTurn?.start?.time;
        if (typeof start === 'number' && typeof end === 'number') {
          durationMs = Math.max(0, end - start);
        }
      }

      return {
        turnCount: turnOrder.length,
        stepCount,
        userCount,
        assistantCount,
        toolCount,
        commandCount,
        errorCount,
        durationMs,
        isRunning: session?.running === true,
      };
    }

    /**
     * Render one metric card.
     * @param {string} label
     * @param {string | number} value
     */
    function MetricCard({ label, value }) {
      return h('div', {
        style: {
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
          padding: '12px 16px',
          borderRadius: '8px',
          backgroundColor: 'var(--dsw-alias-surface-container, rgba(127,127,127,0.1))',
          minWidth: '96px',
          flex: '1 1 0',
        },
      }, [
        h('span', {
          key: 'label',
          style: {
            fontSize: '12px',
            lineHeight: '16px',
            color: 'var(--dsw-alias-on-surface-variant, inherit)',
          },
        }, label),
        h('span', {
          key: 'value',
          style: {
            fontSize: '20px',
            lineHeight: '28px',
            fontWeight: 600,
            color: 'var(--dsw-alias-on-surface, inherit)',
          },
        }, String(value)),
      ]);
    }

    /**
     * The Insight view component.
     * @param {object} props
     */
    function InsightView(props) {
      const { useSession, useChat, t } = props;
      const session = useSession(s => s);
      const chat = useChat(c => c);
      const [isVisible, setIsVisible] = React.useState(false);

      React.useEffect(() => {
        setIsVisible(true);
        return () => setIsVisible(false);
      }, []);

      if (session == null) {
        return h('div', {
          style: {
            padding: '48px 24px',
            textAlign: 'center',
            color: 'var(--dsw-alias-on-surface-variant, inherit)',
          },
        }, [
          h('h3', { key: 'title', style: { margin: '0 0 8px' } }, t('empty.title')),
          h('p', { key: 'body', style: { margin: 0 } }, t('empty.body')),
        ]);
      }

      const insight = deriveInsight(chat, session);
      const statusKey = insight.isRunning
        ? 'status.running'
        : insight.turnCount === 0
          ? 'status.blank'
          : 'status.idle';

      return h('div', {
        style: {
          display: 'flex',
          flexDirection: 'column',
          gap: '24px',
          padding: '24px',
          color: 'var(--dsw-alias-on-surface, inherit)',
          fontFamily: 'var(--dsw-alias-font-family, inherit)',
          opacity: isVisible ? 1 : 0,
          transition: 'opacity 200ms ease-out',
        },
      }, [
        h('div', {
          key: 'header',
          style: {
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '16px',
          },
        }, [
          h('h2', {
            style: {
              margin: 0,
              fontSize: '18px',
              lineHeight: '24px',
              fontWeight: 600,
            },
          }, t('title')),
          h('span', {
            style: {
              fontSize: '12px',
              lineHeight: '16px',
              padding: '4px 10px',
              borderRadius: '9999px',
              backgroundColor: insight.isRunning
                ? 'var(--dsw-alias-primary-container, rgba(36,123,191,0.15))'
                : 'var(--dsw-alias-surface-container-highest, rgba(127,127,127,0.15))',
              color: insight.isRunning
                ? 'var(--dsw-alias-on-primary-container, inherit)'
                : 'var(--dsw-alias-on-surface-variant, inherit)',
            },
          }, t(statusKey)),
        ]),

        h('div', {
          key: 'grid',
          style: {
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))',
            gap: '12px',
          },
        }, [
          h(MetricCard, { key: 'turns', label: t('metrics.turns'), value: insight.turnCount }),
          h(MetricCard, { key: 'steps', label: t('metrics.steps'), value: insight.stepCount }),
          h(MetricCard, { key: 'messages', label: t('metrics.messages'), value: insight.userCount + insight.assistantCount }),
          h(MetricCard, { key: 'tools', label: t('metrics.tools'), value: insight.toolCount }),
          h(MetricCard, { key: 'commands', label: t('metrics.commands'), value: insight.commandCount }),
          h(MetricCard, { key: 'errors', label: t('metrics.errors'), value: insight.errorCount }),
        ]),

        h('div', {
          key: 'detail',
          style: {
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            padding: '16px',
            borderRadius: '8px',
            backgroundColor: 'var(--dsw-alias-surface-container-low, rgba(127,127,127,0.06))',
          },
        }, [
          h('div', { key: 'row1', style: { display: 'flex', justifyContent: 'space-between' } }, [
            h('span', null, t('metrics.user')),
            h('strong', null, insight.userCount),
          ]),
          h('div', { key: 'row2', style: { display: 'flex', justifyContent: 'space-between' } }, [
            h('span', null, t('metrics.assistant')),
            h('strong', null, insight.assistantCount),
          ]),
          h('div', { key: 'row3', style: { display: 'flex', justifyContent: 'space-between' } }, [
            h('span', null, t('metrics.duration')),
            h('strong', null, formatDuration(insight.durationMs, t)),
          ]),
        ]),
      ]);
    }

    function apply(ctx) {
      ctx.effect(() => ctx.locale.register(NS, { en, zh }), 'conv-insight: dictionaries');
      const t = ctx.locale.bind(NS);

      ctx.slots.inject('conversation.view', () => ctx.slots.register({
        name: 'conversation.view',
        id: 'insight',
        order: 25,
        locale: NS,
        label: () => t('view.insight'),
      }, InsightView));
    }

    return {
      inject: ['slots', 'uiSession', 'locale'],
      apply,
    };
  },
});
