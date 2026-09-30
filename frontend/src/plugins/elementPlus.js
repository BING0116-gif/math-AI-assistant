import { ElAlert } from 'element-plus/es/components/alert/index'
import { ElButton } from 'element-plus/es/components/button/index'
import { ElCheckbox } from 'element-plus/es/components/checkbox/index'
import { ElDialog } from 'element-plus/es/components/dialog/index'
import { ElDivider } from 'element-plus/es/components/divider/index'
import { ElDrawer } from 'element-plus/es/components/drawer/index'
import { ElInput } from 'element-plus/es/components/input/index'
import { ElInputNumber } from 'element-plus/es/components/input-number/index'
import { ElLink } from 'element-plus/es/components/link/index'
import { ElOption } from 'element-plus/es/components/select/index'
import { ElProgress } from 'element-plus/es/components/progress/index'
import { ElRadioButton, ElRadioGroup } from 'element-plus/es/components/radio/index'
import { ElSelect } from 'element-plus/es/components/select/index'
import { ElSwitch } from 'element-plus/es/components/switch/index'
import { ElTabPane, ElTabs } from 'element-plus/es/components/tabs/index'
import { ElTable, ElTableColumn } from 'element-plus/es/components/table/index'
import { ElTag } from 'element-plus/es/components/tag/index'
import { ElTimeline, ElTimelineItem } from 'element-plus/es/components/timeline/index'

import 'element-plus/theme-chalk/base.css'
import 'element-plus/theme-chalk/el-alert.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-checkbox.css'
import 'element-plus/theme-chalk/el-dialog.css'
import 'element-plus/theme-chalk/el-divider.css'
import 'element-plus/theme-chalk/el-drawer.css'
import 'element-plus/theme-chalk/el-input.css'
import 'element-plus/theme-chalk/el-input-number.css'
import 'element-plus/theme-chalk/el-link.css'
import 'element-plus/theme-chalk/el-message.css'
import 'element-plus/theme-chalk/el-message-box.css'
import 'element-plus/theme-chalk/el-option.css'
import 'element-plus/theme-chalk/el-progress.css'
import 'element-plus/theme-chalk/el-radio-button.css'
import 'element-plus/theme-chalk/el-radio-group.css'
import 'element-plus/theme-chalk/el-select.css'
import 'element-plus/theme-chalk/el-switch.css'
import 'element-plus/theme-chalk/el-table.css'
import 'element-plus/theme-chalk/el-tabs.css'
import 'element-plus/theme-chalk/el-tag.css'
import 'element-plus/theme-chalk/el-timeline.css'
import 'element-plus/theme-chalk/dark/css-vars.css'

const components = [
  ElAlert, ElButton, ElCheckbox, ElDialog, ElDivider, ElDrawer, ElInput,
  ElInputNumber, ElLink, ElOption, ElProgress, ElRadioButton, ElRadioGroup,
  ElSelect, ElSwitch, ElTabPane, ElTable, ElTableColumn, ElTabs, ElTag,
  ElTimeline, ElTimelineItem,
]

export function setElementPlusApp(app) {
  components.forEach((component) => app.component(component.name, component))
}

export async function ensureElementPlus() {
  // Kept as a compatibility boundary for existing lazy admin routes.
  return Promise.resolve()
}

export async function loadAdminView(loader) {
  await ensureElementPlus()
  return loader()
}
