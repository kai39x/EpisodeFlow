; EpisodeFlow installer (NSIS 3). build.bat makes it:
;   makensis /DVERSION=1.2.0 installer\EpisodeFlow.nsi   ->   release\EpisodeFlow-Setup.exe
; Installs for the current user only (no admin prompt) into %LOCALAPPDATA%\Programs\EpisodeFlow.
; Your history and settings live in %LOCALAPPDATA%\EpisodeFlow, the same place the portable
; EpisodeFlow.exe uses, so switching between the two keeps them.

Unicode true
ManifestDPIAware true
SetCompressor /SOLID lzma

!ifndef VERSION
  !define VERSION "0.0.0"
!endif
!define APP "EpisodeFlow"
!define EXE "EpisodeFlow.exe"
!define UNINST "Uninstall EpisodeFlow.exe"
!define UNKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\EpisodeFlow"
!define REPO "https://github.com/kai39x/EpisodeFlow"

Name "${APP}"
OutFile "..\release\EpisodeFlow-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\${APP}"
InstallDirRegKey HKCU "${UNKEY}" "InstallLocation"
RequestExecutionLevel user
BrandingText "${APP} ${VERSION}"

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APP}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "FileDescription" "${APP} installer"
VIAddVersionKey "LegalCopyright" "MIT License"

!include "MUI2.nsh"
!include "LogicLib.nsh"

!define MUI_ICON "..\assets\EpisodeFlow.ico"
!define MUI_UNICON "..\assets\EpisodeFlow.ico"
!define MUI_ABORTWARNING
!define MUI_COMPONENTSPAGE_NODESC
!define MUI_FINISHPAGE_RUN "$INSTDIR\${EXE}"
!define MUI_FINISHPAGE_LINK "${REPO}"
!define MUI_FINISHPAGE_LINK_LOCATION "${REPO}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Arabic"
!insertmacro MUI_RESERVEFILE_LANGDLL

LangString SecApp ${LANG_ENGLISH} "EpisodeFlow"
LangString SecApp ${LANG_ARABIC} "EpisodeFlow"
LangString SecStart ${LANG_ENGLISH} "Start menu shortcut"
LangString SecStart ${LANG_ARABIC} "اختصار في قائمة ابدأ"
LangString SecDesktop ${LANG_ENGLISH} "Desktop shortcut"
LangString SecDesktop ${LANG_ARABIC} "اختصار على سطح المكتب"
LangString SecSendTo ${LANG_ENGLISH} "Send To menu (right-click a folder, Send to, EpisodeFlow)"
LangString SecSendTo ${LANG_ARABIC} "قائمة Send To (كليك يمين على المجلد ثم Send to ثم EpisodeFlow)"
LangString MsgRunning ${LANG_ENGLISH} "EpisodeFlow is open. Close it, then press Retry."
LangString MsgRunning ${LANG_ARABIC} "EpisodeFlow مفتوح. سكّره وبعدين اضغط Retry."
LangString MsgKeepData ${LANG_ENGLISH} "Also delete your rename history and settings?$\r$\n$\r$\nChoose No to keep them, for example if you'll use EpisodeFlow again. Your anime files are never touched."
LangString MsgKeepData ${LANG_ARABIC} "تبي تحذف سجل التسميات والإعدادات بعد؟$\r$\n$\r$\nاختر No عشان تخليها، مثلاً لو بترجع تستخدم EpisodeFlow. ملفات الأنمي ما تنلمس أبداً."

Function .onInit
  !insertmacro MUI_LANGDLL_DISPLAY
FunctionEnd

Function un.onInit
  !insertmacro MUI_UNGETLANGUAGE
FunctionEnd

; Replace EpisodeFlow.exe, asking to close it first if it's running
!macro ReplaceExe
  retry:
  ClearErrors
  Delete "$INSTDIR\${EXE}"
  ${If} ${Errors}
    MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "$(MsgRunning)" IDRETRY retry
    Abort
  ${EndIf}
!macroend

Section "!$(SecApp)" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  ${If} ${FileExists} "$INSTDIR\${EXE}"
    !insertmacro ReplaceExe
  ${EndIf}
  File "..\release\${EXE}"
  WriteUninstaller "$INSTDIR\${UNINST}"

  WriteRegStr HKCU "${UNKEY}" "DisplayName" "${APP}"
  WriteRegStr HKCU "${UNKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNKEY}" "Publisher" "${APP}"
  WriteRegStr HKCU "${UNKEY}" "DisplayIcon" "$\"$INSTDIR\${EXE}$\",0"
  WriteRegStr HKCU "${UNKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNKEY}" "UninstallString" "$\"$INSTDIR\${UNINST}$\""
  WriteRegStr HKCU "${UNKEY}" "QuietUninstallString" "$\"$INSTDIR\${UNINST}$\" /S"
  WriteRegStr HKCU "${UNKEY}" "URLInfoAbout" "${REPO}"
  WriteRegDWORD HKCU "${UNKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNKEY}" "NoRepair" 1
  SectionGetSize ${SecMain} $0
  WriteRegDWORD HKCU "${UNKEY}" "EstimatedSize" $0
SectionEnd

Section "$(SecStart)" SecStartMenu
  CreateShortcut "$SMPROGRAMS\${APP}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\${EXE}" 0
SectionEnd

Section "$(SecDesktop)" SecDesk
  CreateShortcut "$DESKTOP\${APP}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\${EXE}" 0
SectionEnd

Section "$(SecSendTo)" SecSend
  CreateShortcut "$APPDATA\Microsoft\Windows\SendTo\${APP}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\${EXE}" 0
SectionEnd

Section "Uninstall"
  retry:
  ClearErrors
  Delete "$INSTDIR\${EXE}"
  ${If} ${Errors}
    MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "$(MsgRunning)" IDRETRY retry
    Abort
  ${EndIf}
  Delete "$INSTDIR\${UNINST}"
  RMDir "$INSTDIR"

  Delete "$SMPROGRAMS\${APP}.lnk"
  Delete "$DESKTOP\${APP}.lnk"
  Delete "$APPDATA\Microsoft\Windows\SendTo\${APP}.lnk"
  DeleteRegKey HKCU "${UNKEY}"

  ; History and settings: only when asked (a silent uninstall keeps them)
  MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 "$(MsgKeepData)" /SD IDNO IDNO keep
    Delete "$LOCALAPPDATA\${APP}\settings.json"
    Delete "$LOCALAPPDATA\${APP}\history.json"
    Delete "$LOCALAPPDATA\${APP}\history.json.tmp"
    Delete "$LOCALAPPDATA\${APP}\anilist_cache.json"
    Delete "$LOCALAPPDATA\${APP}\anilist_cache.json.tmp"
    Delete "$LOCALAPPDATA\${APP}\episodeflow_error.log"
    RMDir /r "$LOCALAPPDATA\${APP}\window-data"
    RMDir /r "$LOCALAPPDATA\${APP}\window"
    RMDir "$LOCALAPPDATA\${APP}"
  keep:
SectionEnd
