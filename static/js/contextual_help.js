(() => {
    'use strict';

    const textsById = {
        scanBtn: 'Сканировать локальную папку оператора, распознать DAT/XML и обновить записи в локальной базе.',
        syncBtn: 'Синхронизировать обработанные лицензии и базу данных с сетевым хранилищем.',
        downloadBtn: 'Загрузить актуальную базу лицензий из сетевого хранилища в локальную копию.',
        importExcelBtn: 'Импортировать лицензии из XLSX/XLS. Проверьте порядок колонок перед загрузкой.',
        loadPresetBtn: 'Открыть сохранённые наборы фильтров, колонок и параметров таблицы.',
        managePresetsBtn: 'Переименовать, удалить или назначить набор настроек по умолчанию.',
        savePresetBtn: 'Сохранить текущие фильтры и параметры таблицы как новый набор.',
        exportPresetsBtn: 'Выгрузить наборы настроек в файл для переноса или резервной копии.',
        importPresetsBtn: 'Загрузить ранее выгруженные наборы настроек из файла.',
        exportExcelBtn: 'Выгрузить текущий список лицензий в Excel с учётом применённых фильтров.',
        colorGroupingBtn: 'Настроить цветовое выделение строк по значениям выбранного поля.',
        columnSettingsBtn: 'Выбрать видимые колонки, их порядок, ширину и оформление таблицы.',
        resetColumnsOrderBtn: 'Вернуть исходный порядок колонок без изменения их видимости.',
        resetColumnWidthsBtn: 'Вернуть ширину колонок к значениям по умолчанию.',
        applyColumnsBtn: 'Применить выбранные настройки таблицы и сохранить их для оператора.',
        cancelColumnsBtn: 'Закрыть настройки без применения внесённых изменений.',
        resetFiltersBtn: 'Очистить все активные фильтры и показать полный список лицензий.',
        bulkDetailBtn: 'Открыть сведения и иерархию ресурсов сразу для выбранных лицензий.',
        bulkAddTagBtn: 'Добавить один тег ко всем выбранным лицензиям.',
        bulkRemoveTagBtn: 'Удалить выбранный тег у всех отмеченных лицензий.',
        bulkExportBtn: 'Экспортировать в Excel только отмеченные лицензии.',
        bulkCloseBtn: 'Снять выделение и закрыть панель групповых действий.',
        presetDefaultBtn: 'Использовать текущие настройки списка как набор по умолчанию.',
        applyColorGroupingBtn: 'Применить выбранные правила цветового выделения к таблице.',
        cancelColorGroupingBtn: 'Закрыть настройку цветов без сохранения изменений.',
        openTableSettingsBtn: 'Настроить отображение таблицы ресурсов и иерархии лицензии.',
        openFolderBtn: 'Открыть папку с выбранным файлом лицензии средствами операционной системы.',
        addTagBtn: 'Создать тег и связать его с текущей лицензией.',
        saveTableSettingsBtn: 'Сохранить параметры отображения таблицы ресурсов.',
        closeSettingsBtn: 'Закрыть настройки таблицы без сохранения.',
        addColumnBtn: 'Создать пользовательскую колонку, значение которой будет извлекаться по правилу.',
        addRuleBtn: 'Добавить правило извлечения динамического поля из содержимого лицензии.',
        resetDefaultsBtn: 'Вернуть стандартное соответствие CapacityKey и листов Excel.',
        resetEsnDefaultsBtn: 'Вернуть стандартное расположение полей ESN-маппинга в колонках A–G.',
        checkEsnFilesBtn: 'Проверить наличие файлов ESN-маппинга в настроенной папке хранилища.',
        saveToTargetBtn: 'Выполнить выбранное переименование и сохранить файлы в целевую папку.',
        cancelBtn: 'Отменить текущую операцию и вернуться без изменения файлов.',
        themeToggleBtn: 'Переключить светлую или тёмную тему интерфейса.',
        createBackupBtn: 'Создать резервную копию локальной базы перед изменением или восстановлением данных.',
        restoreBackupBtn: 'Перейти к списку резервных копий и выбрать файл для восстановления.',
        addDomainBtn: 'Добавить отдельную структуру папок для нового домена.',
        removeDomainBtn: 'Удалить структуру выбранного домена; общая структура default останется.',
        addFolderLevelBtn: 'Добавить выбранное поле как новый уровень вложенности папок.',
        resetFolderStructureBtn: 'Вернуть структуру выбранного домена к стандартному набору уровней.',
        backupOperatorFolderBtn: 'Скопировать папку текущего оператора на сетевом хранилище в каталог _backup.',
        backupDbBtn: 'Создать резервную копию локальной базы лицензий.',
        previewRenameBtn: 'Показать будущие имена файлов без переименования или перемещения.',
        previewMoveBtn: 'Показать будущие пути файлов без изменения содержимого хранилища.',
        previewBothBtn: 'Проверить одновременно новые имена и новые пути без применения изменений.',
        applyRenameBtn: 'Переименовать файлы по результатам предпросмотра. Перед запуском создайте резервную копию.',
        applyMoveBtn: 'Разложить файлы по папкам по результатам предпросмотра. Перед запуском создайте резервную копию.',
        applyBothBtn: 'Переименовать и разложить файлы по результатам предпросмотра. Перед запуском создайте резервную копию.',
        clearLogsBtn: 'Удалить файлы журналов приложения. Сами лицензии и база данных не изменяются.',
        resetDbBtn: 'Полностью пересоздать локальную базу. Сначала создайте резервную копию local_licenses.db.',
        toggleAllBtn: 'Раскрыть или свернуть все категории системных тестов.',
        runAllTestsBtn: 'Запустить все проверки и показать результат по каждому компоненту.',
        refreshTestListBtn: 'Заново загрузить список доступных проверок без запуска тестов.',
        demoDropdownBtn: 'Показать пример раскрывающегося меню набора настроек.',
        demoModalBtn: 'Открыть пример модального окна интерфейса.'
    };

    const tooltip = document.createElement('div');
    tooltip.id = 'contextual-tooltip';
    tooltip.className = 'contextual-tooltip';
    tooltip.setAttribute('role', 'tooltip');
    tooltip.setAttribute('aria-hidden', 'true');
    document.body.appendChild(tooltip);

    let activeTarget = null;

    function getText(target) {
        return target.dataset.tooltip || textsById[target.id] || '';
    }

    function findTarget(node) {
        const element = node instanceof Element ? node : node.parentElement;
        if (!element) return null;
        const target = element.closest('button, a, [role="button"], [data-tooltip]');
        return target && getText(target).trim() ? target : null;
    }

    function positionTooltip(target) {
        const margin = 12;
        const gap = 8;
        const targetRect = target.getBoundingClientRect();
        const tooltipRect = tooltip.getBoundingClientRect();

        let left = targetRect.left + (targetRect.width - tooltipRect.width) / 2;
        left = Math.max(margin, Math.min(left, window.innerWidth - tooltipRect.width - margin));

        let top = targetRect.top - tooltipRect.height - gap;
        if (top < margin) {
            top = targetRect.bottom + gap;
        }
        top = Math.max(margin, Math.min(top, window.innerHeight - tooltipRect.height - margin));

        tooltip.style.left = `${Math.round(left)}px`;
        tooltip.style.top = `${Math.round(top)}px`;
    }

    function showTooltip(target) {
        if (activeTarget === target && tooltip.classList.contains('visible')) return;
        hideTooltip();

        activeTarget = target;
        tooltip.textContent = getText(target);
        tooltip.style.visibility = 'hidden';
        tooltip.classList.add('visible');
        tooltip.setAttribute('aria-hidden', 'false');
        positionTooltip(target);
        tooltip.style.visibility = '';

        const describedBy = new Set((target.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
        describedBy.add(tooltip.id);
        target.setAttribute('aria-describedby', Array.from(describedBy).join(' '));
    }

    function hideTooltip() {
        if (!activeTarget) return;
        const describedBy = (activeTarget.getAttribute('aria-describedby') || '')
            .split(/\s+/)
            .filter(value => value && value !== tooltip.id);
        if (describedBy.length) {
            activeTarget.setAttribute('aria-describedby', describedBy.join(' '));
        } else {
            activeTarget.removeAttribute('aria-describedby');
        }
        activeTarget = null;
        tooltip.classList.remove('visible');
        tooltip.setAttribute('aria-hidden', 'true');
        tooltip.textContent = '';
    }

    document.addEventListener('pointerover', event => {
        if (event.pointerType === 'touch') return;
        const target = findTarget(event.target);
        if (!target || target.contains(event.relatedTarget)) return;
        showTooltip(target);
    });

    document.addEventListener('pointerout', event => {
        if (!activeTarget || activeTarget.contains(event.relatedTarget)) return;
        hideTooltip();
    });

    document.addEventListener('pointerdown', event => {
        if (event.pointerType !== 'touch') return;
        const target = findTarget(event.target);
        if (target) showTooltip(target);
        else hideTooltip();
    });

    document.addEventListener('focusin', event => {
        const target = findTarget(event.target);
        if (target) showTooltip(target);
    });

    document.addEventListener('focusout', event => {
        if (activeTarget === event.target) hideTooltip();
    });

    document.addEventListener('keydown', event => {
        if (event.key === 'Escape') hideTooltip();
    });

    window.addEventListener('scroll', hideTooltip, true);
    window.addEventListener('resize', hideTooltip);
})();
