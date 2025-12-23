/* Quill エディター用追加スタイル */

// カラーパレット
const colors = [
    '#000000', '#e60000', '#ff9900', '#ffff00', '#008a00', '#0066cc', '#9933ff',
    '#ffffff', '#facccc', '#ffebcc', '#ffffcc', '#cce8cc', '#cce0f5', '#ebd6ff',
    '#bbbbbb', '#f06666', '#ffc266', '#ffff66', '#66b966', '#66a3e0', '#c285ff',
    '#888888', '#a10000', '#b26b00', '#b2b200', '#006100', '#0047b2', '#6b24b2',
    '#444444', '#5c0000', '#663d00', '#666600', '#003700', '#002966', '#3d1466'
];

// エディター初期化
function initEditor(elementId, readOnly = false) {
    const toolbarOptions = readOnly ? false : [
        [{ 'header': [1, 2, 3, false] }],
        ['bold', 'italic', 'underline', 'strike'],
        [{ 'color': colors }, { 'background': colors }],
        [{ 'list': 'ordered' }, { 'list': 'bullet' }],
        [{ 'indent': '-1' }, { 'indent': '+1' }],
        ['blockquote', 'code-block'],
        ['link', 'image'],
        ['clean']
    ];

    const quill = new Quill(`#${elementId}`, {
        theme: 'snow',
        readOnly: readOnly,
        modules: {
            toolbar: toolbarOptions
        },
        placeholder: readOnly ? '' : 'ここに入力してください...'
    });

    return quill;
}

// エディターの内容を取得
function getEditorContent(quill) {
    return quill.root.innerHTML;
}

// エディターに内容を設定
function setEditorContent(quill, content) {
    quill.root.innerHTML = content;
}

// フォーム送信時にエディターの内容を隠しフィールドに設定
function setupEditorForm(formId, editorQuill, hiddenFieldId) {
    const form = document.getElementById(formId);
    if (form) {
        form.addEventListener('submit', function (e) {
            const hiddenField = document.getElementById(hiddenFieldId);
            hiddenField.value = getEditorContent(editorQuill);
        });
    }
}

// アラートの自動非表示
document.addEventListener('DOMContentLoaded', function () {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-10px)';
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    });
});

// 削除確認ダイアログ
function confirmDelete(message = 'この操作は取り消せません。本当に削除しますか？') {
    return confirm(message);
}
