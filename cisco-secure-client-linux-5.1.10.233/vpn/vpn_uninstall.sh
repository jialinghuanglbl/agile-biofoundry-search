#!/bin/sh

AC_INSTPREFIX="/opt/cisco/anyconnect"
INSTPREFIX="/opt/cisco/secureclient"
NVM_DIR="${INSTPREFIX}/NVM"
ROOTCERTSTORE=/opt/.cisco/certificates/ca
ROOTCACERT="DigiCertAssuredIDRootCA.pem"
ROOTCACERT_OLD="VeriSignClass3PublicPrimaryCertificationAuthority-G5.pem"
BINDIR="${INSTPREFIX}/bin"
LIBDIR="${INSTPREFIX}/lib"
PROFDIR="${INSTPREFIX}/vpn/profile"
SCRIPTDIR="${INSTPREFIX}/vpn/script"
HELPDIR="${INSTPREFIX}/help"
PLUGINDIR="${BINDIR}/plugins"
MENUDIR="/etc/xdg/menus/applications-merged/"
DIRECTORYDIR="/usr/share/desktop-directories/"
DESKTOPDIR="/usr/share/applications"
ICONSDIR="/usr/share/icons"
SYSTEMD_CONF="vpnagentd.service"
SYSTEMD_CONF_DIR="/etc/systemd/system"
AGENT="vpnagentd"
VPNMANIFEST="ACManifestVPN.xml"
LOGDIR="/var/log/secureclient"
UNINSTALLLOG="${LOGDIR}/csc_vpn_uninstall.log"

# List of files to remove
FILELIST="${BINDIR}/vpnagentd \
          ${BINDIR}/vpn_uninstall.sh \
          ${BINDIR}/cisco_secure_client_uninstall.sh \
          ${LIBDIR}/libacciscossl.so \
          ${LIBDIR}/libacciscocrypto.so \
          ${LIBDIR}/cfom.so \
          ${LIBDIR}/libaccurl.so.4 \
          ${LIBDIR}/libaccurl.so.4.8.0 \
          ${LIBDIR}/libvpnagentutilities.so \
          ${LIBDIR}/libvpncommon.so \
          ${LIBDIR}/libvpncommoncrypt.so \
          ${LIBDIR}/libvpnapi.so \
          ${LIBDIR}/libacruntime.so \
          ${BINDIR}/vpnui \
          ${BINDIR}/vpn \
          ${BINDIR}/vpndownloader \
          ${BINDIR}/vpndownloader-cli \
          ${PLUGINDIR}/libacdownloader.so \
          ${BINDIR}/acinstallhelper \
          ${BINDIR}/acwebhelper \
          ${BINDIR}/acextwebhelper \
          ${BINDIR}/manifesttool \
          ${BINDIR}/manifesttool_vpn \
          ${BINDIR}/load_tun.sh \
          ${MENUDIR}/cisco-secure-client.menu \
          ${DIRECTORYDIR}/cisco-secure-client.directory \
          ${DESKTOPDIR}/com.cisco.secureclient.gui.desktop \
          ${ICONSDIR}/hicolor/48x48/apps/cisco-secure-client.png \
          ${ICONSDIR}/hicolor/64x64/apps/cisco-secure-client.png \
          ${ICONSDIR}/hicolor/96x96/apps/cisco-secure-client.png \
          ${ICONSDIR}/hicolor/128x128/apps/cisco-secure-client.png \
          ${ICONSDIR}/hicolor/256x256/apps/cisco-secure-client.png \
          ${ICONSDIR}/hicolor/512x512/apps/cisco-secure-client.png \
          ${INSTPREFIX}/resources/* \
          ${INSTPREFIX}/${VPNMANIFEST} \
          ${INSTPREFIX}/update.txt \
          ${INSTPREFIX}/OpenSource.html \
          ${PROFDIR}/AnyConnectProfile.xsd \
          ${INSTPREFIX}/AnyConnectLocalPolicy.xsd \
          ${LIBDIR}/libboost_date_time.so* \
          ${LIBDIR}/libboost_atomic.so* \
          ${LIBDIR}/libboost_filesystem.so* \
          ${LIBDIR}/libboost_system.so* \
          ${LIBDIR}/libboost_thread.so* \
          ${LIBDIR}/libboost_chrono.so* \
          ${LIBDIR}/libboost_regex.so* \
          ${PLUGINDIR}/libvpnipsec.so \
          ${PLUGINDIR}/libacfeedback.so \
          ${PLUGINDIR}/libacwebhelper.so \
          ${ROOTCERTSTORE}/${ROOTCACERT} \
          ${ROOTCERTSTORE}/${ROOTCACERT_OLD} \
          ${AC_INSTPREFIX}/${VPNMANIFEST} \
          ${SYSTEMD_CONF_DIR}/${SYSTEMD_CONF}"

# Create log directory if not exist
if [ ! -d ${LOGDIR} ]; then
  mkdir -p ${LOGDIR} >/dev/null 2>&1
fi

echo "Uninstalling Cisco Secure Client..."
echo "Uninstalling Cisco Secure Client..." > ${UNINSTALLLOG}
echo `whoami` "invoked $0 from " `pwd` " at " `date` >> ${UNINSTALLLOG}

# Check for root privileges
if [ `id | sed -e 's/(.*//'` != "uid=0" ]; then
  echo "Sorry, you need super user privileges to run this script."
  echo "Sorry, you need super user privileges to run this script." >> ${UNINSTALLLOG}
  exit 1
fi

# update the VPNManifest.dat
echo "${BINDIR}/manifesttool_vpn -x ${INSTPREFIX} ${INSTPREFIX}/${VPNMANIFEST}" >> ${UNINSTALLLOG}
${BINDIR}/manifesttool_vpn -x ${INSTPREFIX} ${INSTPREFIX}/${VPNMANIFEST} >> ${UNINSTALLLOG}

# Attempt to stop the service if it is running.
echo "Stopping the VPN agent..." >> ${UNINSTALLLOG}
TESTINIT=`ls -l /proc/1/exe`
if [ -z "${TESTINIT##*"systemd"*}" ]; then
  echo systemctl stop ${SYSTEMD_CONF} >> ${UNINSTALLLOG}
  systemctl stop ${SYSTEMD_CONF} >> ${UNINSTALLLOG} 2>&1
  echo systemctl disable ${SYSTEMD_CONF} >> ${UNINSTALLLOG}
  systemctl disable ${SYSTEMD_CONF} >> ${UNINSTALLLOG} 2>&1
fi

logger "Stopping the VPN agent..."
max_seconds_to_wait=10
ntests=$max_seconds_to_wait
# Wait up to max_seconds_to_wait seconds for the agent to finish.
while [ -n "`ps -A -o command | grep \"/opt/cisco/secureclient/bin/${AGENT}\" | grep -v 'grep'`" ]
  do
      ntests=`expr  $ntests - 1`
      if [ $ntests -eq 0 ]; then
        logger "Timeout waiting for agent to stop."
        echo "Timeout waiting for agent to stop." >> ${UNINSTALLLOG}
        break
      fi
      sleep 1
  done

# ensure that the agent, gui and cli are not running
OURPROCS=`ps -A -o pid,command | grep '/opt/cisco/secureclient/bin' | grep -E -v 'grep|vpn_uninstall|cisco_secure_client_uninstall' | awk '{print $1}'`
if [ -n "${OURPROCS}" ] ; then
    for DOOMED in ${OURPROCS}; do
        echo Killing `ps -A -o pid,command -p ${DOOMED} | grep ${DOOMED} | grep -E -v 'ps|grep'` >> ${UNINSTALLLOG}
        kill -KILL ${DOOMED} >> ${UNINSTALLLOG} 2>&1
    done
fi

# Remove only those files that we know we installed
for FILE in ${FILELIST}; do
  echo "rm -f ${FILE}" >> ${UNINSTALLLOG}
  rm -f ${FILE} >> ${UNINSTALLLOG} 2>&1
done

# Remove desktop file in Autostart Directory
if [ -z "$XDG_CONFIG_DIRS" ]; then
    AUTOSTART_DIR=/etc/xdg/autostart
else
    AUTOSTART_DIR=$XDG_CONFIG_DIRS
fi
echo "rm -f $AUTOSTART_DIR/com.cisco.secureclient.gui.desktop" >> ${UNINSTALLLOG}
rm -f $AUTOSTART_DIR/com.cisco.secureclient.gui.desktop >> ${UNINSTALLLOG} 2>&1

# Remove the plugins directory
echo "rm -rf ${PLUGINDIR}" >> ${UNINSTALLLOG}
rm -rf ${PLUGINDIR} >> ${UNINSTALLLOG} 2>&1

# Remove the bin directory if it is empty
echo "rmdir --ignore-fail-on-non-empty ${BINDIR}" >> ${UNINSTALLLOG}
rmdir --ignore-fail-on-non-empty ${BINDIR} >> ${UNINSTALLLOG} 2>&1

# Remove the lib directory if it is empty
echo "rmdir --ignore-fail-on-non-empty ${LIBDIR}" >> ${UNINSTALLLOG}
rmdir --ignore-fail-on-non-empty ${LIBDIR} >> ${UNINSTALLLOG} 2>&1

# Remove the script directory if it is empty
echo "rmdir --ignore-fail-on-non-empty ${SCRIPTDIR}" >> ${UNINSTALLLOG}
rmdir --ignore-fail-on-non-empty ${SCRIPTDIR} >> ${UNINSTALLLOG} 2>&1

# Remove the help directory if it is empty
echo "rmdir --ignore-fail-on-non-empty ${HELPDIR}" >> ${UNINSTALLLOG}
rmdir --ignore-fail-on-non-empty ${HELPDIR} >> ${UNINSTALLLOG} 2>&1

# Remove the profile directory if it is empty
echo "rmdir --ignore-fail-on-non-empty ${PROFDIR}" >> ${UNINSTALLLOG}
rmdir --ignore-fail-on-non-empty ${PROFDIR} >> ${UNINSTALLLOG} 2>&1

# Remove the cert store directory if it is empty
echo "rmdir --ignore-fail-on-non-empty ${ROOTCERTSTORE}" >> ${UNINSTALLLOG}
rmdir --ignore-fail-on-non-empty ${ROOTCERTSTORE} >> ${UNINSTALLLOG} 2>&1

# update the menu cache so that the Cisco Secure Client short cut in the
# applications menu is removed. This is neccessary on some
# gnome desktops(Ubuntu 10.04)
if [ -x "/usr/share/gnome-menus/update-gnome-menus-cache" ]; then
    for CACHE_FILE in $(ls /usr/share/applications/desktop.*.cache); do
        echo "updating ${CACHE_FILE}" >> ${UNINSTALLLOG}
        /usr/share/gnome-menus/update-gnome-menus-cache /usr/share/applications/ > ${CACHE_FILE}
    done
fi

echo "Updating GTK icon cache" >> ${UNINSTALLLOG}
gtk-update-icon-cache -f -t /usr/share/icons/hicolor >> ${UNINSTALLLOG} 2>&1

echo "Successfully removed Cisco Secure Client from the system." >> ${UNINSTALLLOG}
echo "Successfully removed Cisco Secure Client from the system."
exit 0

