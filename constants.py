# -*- coding: utf-8 -*-
"""常量配置：GIF 列表、画画序列、AI 配置模板等"""

# 桌宠使用的 GIF 顺序，索引与 gif/ 目录对应
GIF_NAMES = ['待机.gif', '得意.gif', '思考.gif', '拿笔待机.gif', '期待.gif', '连续绘制.gif', '间歇绘制.gif']

# 画画动画序列：拿笔待机 -> 思考 -> 间歇绘制 -> 连续绘制 -> 间歇绘制 -> 得意
DRAW_SEQUENCE = [3, 2, 6, 5, 6, 1]

# 画画动画中固定步骤的停留时长（毫秒），其余步骤随机 3~10 秒
SPECIAL_DURATIONS = {3: 2000, 5: 3400, 6: 1800}

# 单击互动时可能切换的表情（得意/思考/期待）
CLICK_REACTION_OPTIONS = [1, 2, 4]

# ============ 使用者性别与称谓 ============
# 首次启动需选择性别，称谓随性别变化（未设置时默认叫"共犯"）
GENDER_FILE = '使用者.json'
GENDER_ADDRESS = {'男': '我的共犯先生', '女': '我的共犯小姐'}

# ============ AI 聊天配置 ============
AI_CONFIG_FILE = 'AI配置.json'
AI_CONFIG_TEMPLATE = {
    'base_url': 'https://open.bigmodel.cn/api/paas/v4',
    'api_key': '',
    'model': 'glm-4-flash',
    'vision_model': 'glm-4v-flash',
    'system_prompt': ('你是小蕾米，住在 Windows 桌面上的小桌宠，是共犯最靠谱的搭档。'
                      '说话调皮搞怪、爱接梗、偶尔吐槽，中二但嘴硬心软，'
                      '阴阳怪气里藏着对对方的关心。'
                      '回答尽量简短活泼，不超过 100 字，偶尔带点可爱的语气词，'
                      '默认使用简体中文。'),
    'max_history': 10,
}
