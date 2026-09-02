"""Invite to Campaign 弹窗专用选择器。"""

# 卡片（hover 后 Invite to Campaign 按钮会显示）
CARD_SELECTORS = [
    "css:.iui-card",
]

# Invite to Campaign 按钮
INVITE_BUTTON_SELECTORS = [
    'css:button[data-testid*="invite-campaign"]',
    "text:Invite to Campaign",
]

# 弹窗容器
MODAL_SELECTORS = [
    "css:.iui-modal.uicc-modal-invite-campaign",
]

# 弹窗内的 campaign Select 按钮
CAMPAIGN_SELECT_BUTTON_SELECTORS = [
    "css:.iui-multi-select-input-button",
    "text:Select",
]

# campaign 下拉浮层
CAMPAIGN_DROPDOWN_SELECTORS = [
    "css:.campaign-select-dropdown",
]

# campaign 下拉选项
CAMPAIGN_OPTION_SELECTORS = [
    "css:li[role='option']",
]

# Personalized Message 文本框
MESSAGE_TEXTAREA_SELECTORS = [
    'css:textarea[data-testid="uicl-textarea"]',
    "tag:textarea",
]

# Partner Groups tag 输入框（与 Send Proposal 弹窗同款 uicl 组件）
PARTNER_GROUP_INPUT_SELECTORS = [
    'css:input[data-testid="uicl-tag-input-text-input"]',
    'css:[data-testid="uicl-tag-input"] input',
    "css:.iui-tag-input input",
]

# Partner Groups 下拉浮层（新版独立浮层 / tag-input 容器内两种布局）
PARTNER_GROUP_DROPDOWN_SELECTORS = [
    'css:[data-testid="uicl-tag-input-dropdown"]',
]

PARTNER_GROUP_OPTION_SELECTORS = [
    'css:li[role="option"]',
    'css:div[role="option"]',
    "css:li",
]

# Send Invite 按钮
SEND_INVITE_BUTTON_SELECTORS = [
    "text:Send Invite",
]

# 邀请 API URL 关键词（用于网络监听过滤）
INVITE_API_URL_KEYWORD = "campaign/partner/invite"
