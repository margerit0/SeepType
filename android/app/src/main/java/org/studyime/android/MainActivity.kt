// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android

import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.text.InputType
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.EditText
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.WindowCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.studyime.android.clipboard.ClipboardHistoryRepository
import org.studyime.android.engine.schemaName
import org.studyime.android.settings.KeyboardPreferences
import org.studyime.android.settings.KeyboardSkin
import org.studyime.android.settings.Preferences
import org.studyime.android.ui.LocalStudyColors
import org.studyime.android.ui.StudyTheme

@OptIn(ExperimentalComposeUiApi::class)
class MainActivity : ComponentActivity() {
    private var enabled by mutableStateOf(false)
    private var selected by mutableStateOf(false)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val settings = remember { Preferences.get(this) }
            val prefs by settings.state.collectAsState()
            var screen by rememberSaveable { mutableStateOf(intent.getStringExtra("screen")?.takeIf { it in listOf("practice", "settings", "about") } ?: "home") }
            var license by rememberSaveable { mutableStateOf("") }
            StudyTheme(prefs.theme, prefs.skin) {
                val colors = LocalStudyColors.current
                SideEffect {
                    WindowCompat.getInsetsController(window, window.decorView).apply {
                        isAppearanceLightStatusBars = !colors.dark
                        isAppearanceLightNavigationBars = !colors.dark
                    }
                }
                BackHandler(screen != "home") { if (license.isNotEmpty()) license = "" else screen = "home" }
                Surface(Modifier.fillMaxSize().semantics { testTagsAsResourceId = true }, color = colors.paper) {
                    Column(Modifier.safeDrawingPadding().imePadding()) {
                        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp).heightIn(min = 60.dp), verticalAlignment = Alignment.CenterVertically) {
                            if (screen != "home") IconButton(onClick = { if (license.isNotEmpty()) license = "" else screen = "home" }) {
                                Icon(Icons.AutoMirrored.Outlined.ArrowBack, "返回")
                            }
                            Text(when (screen) { "settings" -> "键盘设置"; "about" -> if (license.isEmpty()) "关于拾词" else "开源许可"; "practice" -> "随手记"; else -> "拾词" },
                                Modifier.weight(1f).padding(start = 8.dp), color = colors.ink, fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
                            if (screen == "home") IconButton(onClick = { screen = "settings" }) { Icon(Icons.Outlined.Settings, "设置") }
                        }
                        when (screen) {
                            "home" -> Welcome(enabled, selected, onEnable = { startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS)) },
                                onChoose = { (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).showInputMethodPicker() },
                                onPractice = { screen = "practice" }, onAbout = { screen = "about" })
                            "settings" -> SettingsScreen(prefs, settings::update) { screen = "about" }
                            "practice" -> PracticeScreen()
                            "about" -> AboutScreen(license) { license = it }
                        }
                    }
                }
            }
        }
    }
    override fun onResume() {
        super.onResume()
        val manager = getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager
        enabled = manager.enabledInputMethodList.any { it.packageName == packageName }
        selected = Settings.Secure.getString(contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)?.startsWith("$packageName/") == true
    }
}

@Composable
private fun Welcome(enabled: Boolean, selected: Boolean, onEnable: () -> Unit, onChoose: () -> Unit, onPractice: () -> Unit, onAbout: () -> Unit) {
    val c = LocalStudyColors.current
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 24.dp)) {
        Spacer(Modifier.height(22.dp))
        Box(Modifier.size(64.dp).clip(RoundedCornerShape(20.dp)).background(c.tint), contentAlignment = Alignment.Center) {
            Icon(Icons.Outlined.Spa, null, Modifier.size(34.dp), tint = c.accent)
        }
        Spacer(Modifier.height(20.dp))
        Text("照常输入，\n顺便拾起一个词。", fontSize = 30.sp, lineHeight = 42.sp, fontWeight = FontWeight.SemiBold, color = c.ink)
        Spacer(Modifier.height(12.dp))
        Text("熟悉的中文键盘，多一行英文释义。\n点按候选输入中文，长按看看完整英文。", fontSize = 14.sp, lineHeight = 23.sp, color = c.subtle)
        Spacer(Modifier.height(28.dp))
        SetupStep("1", "启用拾词", if (enabled) "已在系统中启用" else "允许拾词作为你的输入法", enabled, onEnable)
        Spacer(Modifier.height(10.dp))
        SetupStep("2", "切换键盘", if (selected) "拾词正在使用中" else "选择拾词，开始自在输入", selected, onChoose, enabled)
        Spacer(Modifier.height(22.dp))
        Button(onClick = onPractice, shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth().heightIn(min = 54.dp).testTag("practice_button")) {
            Text("试打几句", fontSize = 16.sp)
        }
        Spacer(Modifier.height(24.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.WifiOff, null, Modifier.size(17.dp), tint = c.subtle)
            Spacer(Modifier.width(8.dp))
            Text("离线运行 · 中文选词只记在本机", fontSize = 12.sp, color = c.subtle)
        }
        TextButton(onClick = onAbout, contentPadding = PaddingValues(vertical = 12.dp), modifier = Modifier.heightIn(min = 48.dp)) {
            Text("开发预览 ${BuildConfig.VERSION_NAME}  ·  词库与许可", fontSize = 11.sp, color = c.subtle)
        }
        Spacer(Modifier.height(14.dp))
    }
}

@Composable
private fun SetupStep(number: String, title: String, subtitle: String, done: Boolean, onClick: () -> Unit, enabled: Boolean = true) {
    val c = LocalStudyColors.current
    Surface(Modifier.fillMaxWidth().clip(RoundedCornerShape(17.dp)).clickable(enabled = enabled, onClick = onClick),
        color = if (done) c.tint.copy(alpha = .55f) else c.key, shape = RoundedCornerShape(17.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, c.line)) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(34.dp).clip(RoundedCornerShape(11.dp)).background(c.function), contentAlignment = Alignment.Center) {
                if (done) Icon(Icons.Outlined.Check, "已完成", Modifier.size(19.dp), tint = c.accent)
                else Text(number, color = c.accent, fontWeight = FontWeight.Medium)
            }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(title, fontSize = 16.sp, color = c.ink, fontWeight = FontWeight.Medium)
                Spacer(Modifier.height(4.dp))
                Text(subtitle, fontSize = 12.sp, lineHeight = 18.sp, color = c.subtle)
            }
            Icon(Icons.Outlined.ChevronRight, null, Modifier.size(21.dp), tint = c.subtle)
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SettingsScreen(prefs: KeyboardPreferences, update: ((KeyboardPreferences) -> KeyboardPreferences) -> Unit, about: () -> Unit) {
    val c = LocalStudyColors.current
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 22.dp)) {
        SettingLabel("拼音方案")
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("study", "study_double_pinyin", "study_flypy").forEach { schema ->
                FilterChip(selected = prefs.schema == schema, onClick = { update { it.copy(schema = schema) } },
                    label = { Text(schemaName(schema), fontSize = 14.sp) }, modifier = Modifier.heightIn(min = 48.dp))
            }
        }
        Text("正在输入时，完成选词后再切换方案。三种方案共用本机选词记录。", fontSize = 12.sp, lineHeight = 20.sp, color = c.subtle)
        Spacer(Modifier.height(16.dp))
        SwitchSetting("显示英文释义", "候选上方显示英文。普通点按和空格仍输入中文。", prefs.showEnglish) { value -> update { it.copy(showEnglish = value) } }
        SwitchSetting("记住中文选词习惯", "只保存在本机；暂停后保留已有词频。长按候选可逐词遗忘。", prefs.userLearning) { value -> update { it.copy(userLearning = value) } }
        ClipboardSettings()
        SettingLabel("皮肤")
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            KeyboardSkin.entries.forEach { skin ->
                FilterChip(selected = prefs.skin == skin, onClick = { update { it.copy(skin = skin) } },
                    label = { Text(skin.title) }, modifier = Modifier.heightIn(min = 48.dp).testTag("settings_skin_${skin.id}"))
            }
        }
        Text("轻彩 · Quicksand 字体与彩色双层键标", fontSize = 12.sp, color = c.subtle)
        SettingLabel("外观")
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("system" to "跟随系统", "light" to "浅色", "dark" to "深色").forEach { (key, name) ->
                FilterChip(selected = prefs.theme == key, onClick = { update { it.copy(theme = key) } }, label = { Text(name) }, modifier = Modifier.heightIn(min = 48.dp))
            }
        }
        Spacer(Modifier.height(10.dp))
        Text("键盘高度", fontSize = 15.sp, color = c.ink)
        Slider(value = prefs.keyHeight, onValueChange = { value -> update { it.copy(keyHeight = value) } }, valueRange = .9f..1.2f, steps = 2)
        Text("显示字号", fontSize = 15.sp, color = c.ink)
        Slider(value = prefs.textScale, onValueChange = { value -> update { it.copy(textScale = value) } }, valueRange = 1f..1.3f, steps = 2)
        Text("同时遵循系统字体大小。", fontSize = 12.sp, color = c.subtle)
        Spacer(Modifier.height(10.dp))
        SwitchSetting("轻微触感", "按键时提供短促反馈。", prefs.haptics) { value -> update { it.copy(haptics = value) } }
        SwitchSetting("减少动态效果", "即时切换状态，减少按压和候选动画。", prefs.reduceMotion) { value -> update { it.copy(reduceMotion = value) } }
        Spacer(Modifier.height(16.dp))
        Text("密码输入会自动关闭释义与选词学习。应用禁止个性化学习时，拾词会暂停记录。用户词典不参与系统云备份或设备迁移。", fontSize = 12.sp, lineHeight = 20.sp, color = c.subtle)
        TextButton(onClick = about, modifier = Modifier.heightIn(min = 52.dp)) { Text("词库、隐私与开源许可") }
        Spacer(Modifier.height(20.dp))
    }
}

@Composable
private fun ClipboardSettings() {
    val context = LocalContext.current
    val repository = remember(context) { ClipboardHistoryRepository.get(context) }
    val state by repository.state.collectAsState()
    var confirmDisable by remember { mutableStateOf(false) }
    SettingLabel("剪贴板")
    SwitchSetting("保存剪贴板历史", "开启后记录复制的文本，最多 50 条，可置顶 10 条。仅存本机，不参与备份；关闭会清空全部历史。",
        state.history.enabled, modifier = Modifier.testTag("settings_clipboard_toggle")) { enabled ->
        if (enabled) repository.setEnabled(true) else confirmDisable = true
    }
    Text("在键盘工具栏打开剪贴板，点按条目即可粘贴。密码和禁止个性化的输入框暂停记录；敏感内容、图片和过长文本不记录。",
        fontSize = 12.sp, lineHeight = 20.sp, color = LocalStudyColors.current.subtle)
    if (state.storageError) Text("暂时无法读写历史，请重试。", color = MaterialTheme.colorScheme.error, fontSize = 12.sp)
    if (confirmDisable) AlertDialog(onDismissRequest = { confirmDisable = false },
        title = { Text("关闭并清空历史？") }, text = { Text("将删除全部剪贴板历史，包括置顶条目。系统剪贴板不受影响。") },
        confirmButton = { TextButton(onClick = { repository.setEnabled(false); confirmDisable = false },
            modifier = Modifier.testTag("settings_clipboard_confirm")) { Text("关闭并清空") } },
        dismissButton = { TextButton(onClick = { confirmDisable = false }) { Text("取消") } })
}

@Composable
private fun SettingLabel(text: String) {
    Text(text, Modifier.padding(top = 18.dp, bottom = 8.dp), fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = LocalStudyColors.current.accent)
}

@Composable
private fun SwitchSetting(title: String, description: String, checked: Boolean, modifier: Modifier = Modifier, onChanged: (Boolean) -> Unit) {
    val c = LocalStudyColors.current
    Row(modifier.fillMaxWidth().heightIn(min = 80.dp).toggleable(checked, role = Role.Switch, onValueChange = onChanged)
        .padding(vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, fontSize = 15.sp, color = c.ink)
            Spacer(Modifier.height(5.dp))
            Text(description, fontSize = 12.sp, lineHeight = 19.sp, color = c.subtle)
        }
        Spacer(Modifier.width(12.dp))
        Switch(checked = checked, onCheckedChange = null)
    }
}

@Composable
private fun PracticeScreen() {
    val c = LocalStudyColors.current
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 25.dp)) {
        Spacer(Modifier.height(18.dp))
        Text("周末的小计划", fontSize = 25.sp, fontWeight = FontWeight.SemiBold, color = c.ink)
        Spacer(Modifier.height(8.dp))
        Text("试着输入 gongyuan，看看双行候选。", fontSize = 12.sp, color = c.subtle)
        Spacer(Modifier.height(20.dp))
        AndroidView(factory = { context -> EditText(context).apply {
            id = R.id.practice_editor
            hint = "写点今天的小事…"
            textSize = 18f
            setPadding(0, 10, 0, 18)
            background = null
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
            imeOptions = EditorInfo.IME_ACTION_NONE
            minLines = 3
            gravity = android.view.Gravity.TOP
        } }, update = { it.setTextColor(c.ink.toArgb()); it.setHintTextColor(c.subtle.toArgb()) },
            modifier = Modifier.fillMaxWidth().heightIn(min = 160.dp))
        HorizontalDivider(color = c.line)
        Spacer(Modifier.height(16.dp))
        Text("点候选的任意一行，都会输入中文。\n长按候选，再点“输入英文”可提交完整英文。", fontSize = 13.sp, lineHeight = 22.sp, color = c.subtle)
        Spacer(Modifier.height(16.dp))
        AndroidView(factory = { context -> EditText(context).apply {
            id = R.id.secondary_editor
            hint = "也可以换个输入位置"
            textSize = 16f
            background = null
            inputType = InputType.TYPE_CLASS_TEXT
            imeOptions = EditorInfo.IME_ACTION_DONE
            setSingleLine(true)
        } }, update = { it.setTextColor(c.ink.toArgb()); it.setHintTextColor(c.subtle.toArgb()) }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(22.dp))
        Text("此页内容不保存，关闭后即可开始新的随手记。", fontSize = 11.sp, color = c.subtle)
    }
}

@Composable
private fun AboutScreen(license: String, select: (String) -> Unit) {
    val c = LocalStudyColors.current
    val context = LocalContext.current
    var body by remember(license) { mutableStateOf("") }
    var dictionary by remember { mutableStateOf<JSONObject?>(null) }
    LaunchedEffect(Unit) {
        dictionary = withContext(Dispatchers.IO) {
            runCatching { context.assets.open("generated/manifest.json").bufferedReader().use { JSONObject(it.readText()) } }.getOrNull()
        }
    }
    LaunchedEffect(license) {
        if (license.isNotEmpty()) body = withContext(Dispatchers.IO) {
            val asset = if (license.startsWith("fonts/")) license else "generated/$license"
            runCatching { context.assets.open(asset).bufferedReader().use { it.readText() } }.getOrDefault("许可文件暂时无法读取。")
        }
    }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 24.dp)) {
        if (license.isNotEmpty()) SelectionContainer { Text(body, fontSize = 13.sp, lineHeight = 21.sp, color = c.ink) }
        else {
            SettingLabel("开发预览")
            Text("拾词 ${BuildConfig.VERSION_NAME}", fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(12.dp))
            val entries = dictionary
            Text(if (entries == null) "正在读取本机词库信息…" else "${"%,d".format(entries.getInt("chineseEntries"))} 条中文候选记录（含读音）\n${"%,d".format(entries.getInt("englishEntries"))} 条英文开发记录", fontSize = 15.sp, lineHeight = 27.sp, color = c.ink)
            entries?.let {
                Text("词库版本 ${it.getString("version")}\n中文快照 ${it.getString("chineseSnapshot")}", fontSize = 11.sp, lineHeight = 18.sp, color = c.subtle)
            }
            Spacer(Modifier.height(12.dp))
            Text("中文候选来自固定的 CC-CEDICT 快照及扩充词库的补充读音。英文释义沿用 Windows 开发词库，仅用于预览，未获人工发布审批。", fontSize = 13.sp, lineHeight = 22.sp, color = c.subtle)
            SettingLabel("只在本机")
            Text("输入、查词与中文选词学习均离线运行。拾词不申请网络权限。选词记录位于应用私有目录，不上传，也不参与 Android 备份。关闭选词学习可暂停新记录；逐词遗忘不修改应用正文。", fontSize = 13.sp, lineHeight = 22.sp, color = c.subtle)
            SettingLabel("开源与数据许可")
            listOf(
                "软件源码 · GPL-3.0-or-later" to "notices/LICENSE",
                "词库数据 · CC BY-SA 4.0" to "notices/chinese/CC-BY-SA-4.0.txt",
                "英文词库来源与审核状态" to "notices/english/NOTICE.txt",
                "词频语料与作者署名" to "notices/chinese/WORDFREQ-README.md",
                "Unicode 数据" to "notices/chinese/UNICODE-LICENSE.txt",
                "Rime 引擎" to "notices/third-party/librime/LICENSE",
                "librime-lua" to "notices/third-party/librime-lua/LICENSE",
                "自然码与小鹤双拼" to "notices/third-party/rime-double-pinyin/LICENSE",
                "组件与数据说明" to "notices/README.txt",
                "第三方组件完整许可" to "notices/THIRD-PARTY.txt",
                "Quicksand 字体 · SIL OFL 1.1" to "fonts/quicksand-OFL.txt",
                "Fredoka 切换键字体 · SIL OFL 1.1" to "fonts/fredoka-OFL.txt",
            ).forEach { (title, path) -> TextButton(onClick = { select(path) }, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                Text(title, Modifier.weight(1f), fontSize = 14.sp)
                Icon(Icons.Outlined.ChevronRight, null, Modifier.size(18.dp))
            } }
        }
        Spacer(Modifier.height(24.dp))
    }
}
