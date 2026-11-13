// SPDX-License-Identifier: GPL-3.0-or-later
package org.studyime.android.ui

import android.view.accessibility.AccessibilityManager
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.ContentPaste
import androidx.compose.material.icons.outlined.DeleteOutline
import androidx.compose.material.icons.outlined.DeleteSweep
import androidx.compose.material.icons.outlined.PushPin
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.flow.collectLatest
import org.studyime.android.clipboard.ClipboardEntry
import org.studyime.android.clipboard.ClipboardHistory
import org.studyime.android.clipboard.ClipboardHistoryState

@Composable
fun ClipboardPanel(
    state: ClipboardHistoryState, modifier: Modifier, canPaste: Boolean,
    onEnabled: (Boolean) -> Unit, onPaste: (String) -> Unit, onPin: (String) -> Unit,
    onDelete: (String) -> Unit, onClear: () -> Unit, close: () -> Unit,
) {
    val colors = LocalStudyColors.current
    val history = state.history
    var confirm by remember { mutableStateOf<String?>(null) }
    val list = rememberLazyListState()
    val view = LocalView.current
    val accessibility = remember(view) { view.context.getSystemService(AccessibilityManager::class.java) }
    LaunchedEffect(history, state.loaded, confirm) { announceImeSubtree(view, accessibility) }
    // LazyColumn preserves the previously visible item's anchor when copies
    // move to the front. New copies/pins should instead reveal the first row.
    LaunchedEffect(history.entries.maxOfOrNull { it.copiedAt }, history.entries.firstOrNull()?.id) {
        if (history.entries.isNotEmpty()) list.scrollToItem(0)
    }
    LaunchedEffect(list) {
        snapshotFlow { list.firstVisibleItemIndex to list.firstVisibleItemScrollOffset }
            .collectLatest { announceImeSubtree(view, accessibility) }
    }
    Column(modifier.background(colors.board).padding(horizontal = 8.dp).testTag("clipboard_panel")) {
        Row(Modifier.fillMaxWidth().height(48.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("剪贴板", Modifier.weight(1f).padding(start = 4.dp), fontSize = 14.sp,
                fontWeight = FontWeight.Medium, color = colors.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text("${history.entries.size}/${ClipboardHistory.MAX_ENTRIES}", fontSize = 10.sp, color = colors.subtle)
            IconButton(onClick = { confirm = "clear" }, enabled = history.entries.isNotEmpty(), modifier = Modifier.size(48.dp).testTag("clipboard_clear")) {
                Icon(Icons.Outlined.DeleteSweep, "清空剪贴板历史", Modifier.size(20.dp),
                    tint = colors.subtle.copy(alpha = if (history.entries.isEmpty()) .4f else 1f))
            }
            Switch(checked = history.enabled, enabled = state.loaded, onCheckedChange = { enabled ->
                if (enabled) onEnabled(true) else confirm = "disable"
            }, modifier = Modifier.heightIn(min = 48.dp).testTag("clipboard_toggle").semantics { contentDescription = "记录剪贴板历史" })
            IconButton(onClick = close, modifier = Modifier.size(48.dp)) {
                Icon(Icons.Outlined.Close, "关闭剪贴板面板", Modifier.size(20.dp), tint = colors.subtle)
            }
        }
        if (state.storageError) Text("历史保存失败，请重试；上次操作未保存。", Modifier.padding(horizontal = 4.dp),
            color = MaterialTheme.colorScheme.error, fontSize = 12.sp)
        when {
            !state.loaded -> Box(Modifier.fillMaxWidth().weight(1f), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp)
            }
            confirm != null -> Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(12.dp)) {
                val disabling = confirm == "disable"
                Text(if (disabling) "关闭并清空全部历史？" else "清空全部历史？", color = colors.ink, fontSize = 15.sp)
                Text("包括置顶条目。系统剪贴板不受影响。", Modifier.padding(top = 4.dp), color = colors.subtle, fontSize = 12.sp)
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = { confirm = null }, modifier = Modifier.heightIn(min = 48.dp)) { Text("取消") }
                    TextButton(onClick = {
                        if (disabling) onEnabled(false) else onClear()
                        confirm = null
                    }, modifier = Modifier.heightIn(min = 48.dp).testTag("clipboard_confirm")) { Text(if (disabling) "关闭并清空" else "清空") }
                }
            }
            !history.enabled -> Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(12.dp),
                horizontalAlignment = Alignment.CenterHorizontally) {
                Text("复制过的文字，随时取用", color = colors.ink, fontSize = 14.sp)
                Text("最多保存 50 条文本，仅存本机。关闭会清空历史。", Modifier.padding(vertical = 5.dp), color = colors.subtle, fontSize = 12.sp)
                Button(onClick = { onEnabled(true) }, modifier = Modifier.heightIn(min = 48.dp).testTag("clipboard_enable")) { Text("开启剪贴板历史") }
            }
            history.entries.isEmpty() -> Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(12.dp),
                horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(Icons.Outlined.ContentPaste, null, Modifier.size(28.dp), tint = colors.subtle)
                Text("还没有复制的文本", Modifier.padding(top = 6.dp), color = colors.ink, fontSize = 14.sp)
                Text("复制文字后会出现在这里。图片、敏感内容和过长文本不记录。", Modifier.padding(top = 5.dp), color = colors.subtle, fontSize = 12.sp)
            }
            else -> LazyColumn(Modifier.weight(1f).fillMaxWidth().testTag("clipboard_list"), state = list,
                contentPadding = PaddingValues(bottom = 6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                items(history.entries, key = { it.id }) { entry ->
                    ClipboardCard(entry, canPaste, entry.pinned || history.entries.count { it.pinned } < ClipboardHistory.MAX_PINNED,
                        onPaste, onPin, onDelete)
                }
            }
        }
    }
}

@Composable
private fun ClipboardCard(entry: ClipboardEntry, canPaste: Boolean, canPin: Boolean, paste: (String) -> Unit, pin: (String) -> Unit, delete: (String) -> Unit) {
    val colors = LocalStudyColors.current
    val time = remember(entry.copiedAt) { SimpleDateFormat("MM-dd HH:mm", Locale.getDefault()).format(Date(entry.copiedAt)) }
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(colors.key).testTag("clipboard_item_${entry.id}"),
        verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f).clickable(enabled = canPaste, role = Role.Button, onClickLabel = "粘贴文本") { paste(entry.id) }
            .heightIn(min = 64.dp).padding(12.dp).testTag("clipboard_text_${entry.id}")) {
            Text(entry.text, color = colors.ink, fontSize = 14.sp, maxLines = 3, overflow = TextOverflow.Ellipsis)
            Text(if (entry.pinned) "已置顶 · $time" else time, Modifier.padding(top = 4.dp), color = colors.subtle, fontSize = 10.sp, maxLines = 1)
        }
        IconButton(onClick = { pin(entry.id) }, enabled = canPin, modifier = Modifier.size(48.dp).testTag("clipboard_pin_${entry.id}")) {
            Icon(Icons.Outlined.PushPin, if (entry.pinned) "取消置顶" else if (canPin) "置顶条目" else "最多置顶 10 条",
                Modifier.size(18.dp), tint = if (entry.pinned) colors.accent else colors.subtle.copy(alpha = if (canPin) 1f else .4f))
        }
        IconButton(onClick = { delete(entry.id) }, modifier = Modifier.size(48.dp).testTag("clipboard_delete_${entry.id}")) {
            Icon(Icons.Outlined.DeleteOutline, "删除条目", Modifier.size(18.dp), tint = colors.subtle)
        }
    }
}
