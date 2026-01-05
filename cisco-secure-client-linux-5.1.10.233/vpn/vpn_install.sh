#!/bin/sh

BASH_BASE_SIZE=0x00000000
CISCO_AC_TIMESTAMP=0x0000000000000000
CISCO_AC_OBJNAME=1234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456
# BASH_BASE_SIZE=0x00000000 is required for signing
# CISCO_AC_TIMESTAMP is also required for signing
# comment is after BASH_BASE_SIZE or else sign tool will find the comment

csc_vercmp() 
{
    ver_from="${1:?missing from-version}"
    ver_to="${2:?missing to-version}"

    if [ "$ver_from" = "$ver_to" ]; then
        echo same
    else
        ver_min="$(printf '%s\n' "$ver_from" "$ver_to" | sort -V | head -n1)"
        if [ "$ver_min" = "$ver_from" ]; then
            echo older
        else
            echo newer
        fi
    fi
}

checkVersionFeasibilityWithStandaloneNVM()
{
  failed=false
  # version of VPN being installed has to be greater than the installed standalone NVM version
  if [ -f ${NVMMANIFEST} ]; then
      VPNVERSION=5.1.10.233
      NVMVERSION=$(awk -F"\"" '/file version/ { print $2 }' ${NVMMANIFEST})

      vpn_ver="$(csc_vercmp "$VPNVERSION" "$NVMVERSION")"
      if [ "$vpn_ver" = older ]; then
        failed=true
      fi
  fi

  if [ "$failed" = true ]; then
      echo "A higher version ${NVMVERSION} of Standalone NVM is already installed!"
      echo "A higher version ${NVMVERSION} of Standalone NVM is already installed!" >> /tmp/${LOGFNAME}
      exitInstallation 1
  fi
}

checkInstalledVersion()
{
  failed=false
  # version of VPN being installed has to be greater than the current VPN version
  if [ -f ${VPNMANIFEST} ]; then
      VPNPREVVERSION=$(awk -F"\"" '/file version/ { print $2 }' ${VPNMANIFEST})
      VPNCURRVERSION=5.1.10.233

      existing_ver="$(csc_vercmp "$VPNPREVVERSION" "$VPNCURRVERSION")"
      if [ "$existing_ver" != older ]; then
        failed=true
      fi
  fi

  if [ "$failed" = true ]; then
    if [ "$existing_ver" = same ]; then
      echo "Version ${VPNCURRVERSION} is already installed!"
      echo "Version ${VPNCURRVERSION} is already installed!" >> /tmp/${LOGFNAME}
    else
      echo "A higher version ${VPNPREVVERSION} of VPN is already installed!"
      echo "A higher version ${VPNPREVVERSION} of VPN is already installed!" >> /tmp/${LOGFNAME}
    fi
    exitInstallation 1
  fi
}

exitInstallation()
{
  echo "Exiting now."
  echo "Exiting now." >> /tmp/${LOGFNAME}

  # move the logfile out of the tmp directory
  mv /tmp/${LOGFNAME} ${INSTPREFIX}/.
  exit $1
}

AC_INSTPREFIX=/opt/cisco/anyconnect
AC_BINDIR=${AC_INSTPREFIX}/bin
AC_UNINST=${AC_BINDIR}/vpn_uninstall.sh

TARROOT="vpn"
INSTPREFIX=/opt/cisco/secureclient
NVM_DIR="${INSTPREFIX}/NVM"
ROOTCERTSTORE=/opt/.cisco/certificates/ca
ROOTCACERT="DigiCertAssuredIDRootCA.pem"
ROOTCACERT_OLD="VeriSignClass3PublicPrimaryCertificationAuthority-G5.pem"
SYSTEMD_CONF="vpnagentd.service"
SYSTEMD_CONF_DIR="/etc/systemd/system"
BINDIR=${INSTPREFIX}/bin
LIBDIR=${INSTPREFIX}/lib
PROFILEDIR=${INSTPREFIX}/vpn/profile
SCRIPTDIR=${INSTPREFIX}/vpn/script
HELPDIR=${INSTPREFIX}/help
PLUGINDIR=${BINDIR}/plugins
UNINST=${BINDIR}/vpn_uninstall.sh
INSTALL=install
PREVDIR=`pwd`
MARKER=$((`grep -an "[B]EGIN\ ARCHIVE" $0 | cut -d ":" -f 1` + 1))
MARKER_END=$((`grep -an "[E]ND\ ARCHIVE" $0 | cut -d ":" -f 1` - 1))
LOGFNAME=`date "+cisco-secure-client-linux64-5.1.10.233-core-vpn-webdeploy-k9-%H%M%S%d%m%Y.log"`
CLIENTNAME="Cisco Secure Client"
FEEDBACK_DIR="${INSTPREFIX}/CustomerExperienceFeedback"

NEWTEMP="."
VPNMANIFEST="${INSTPREFIX}/ACManifestVPN.xml"
NVMMANIFEST="${INSTPREFIX}/ACManifestNVM.xml"
NVMUNINSTALLSCRIPT="${NVM_DIR}/bin/nvm_uninstall.sh"

echo "Installing ${CLIENTNAME}..."
echo "Installing ${CLIENTNAME}..." > /tmp/${LOGFNAME}
echo `whoami` "invoked $0 from " `pwd` " at " `date` >> /tmp/${LOGFNAME}

# Make sure we are root
if [ `id | sed -e 's/(.*//'` != "uid=0" ]; then
  echo "Sorry, you need super user privileges to run this script."
  exitInstallation 1
fi
## The web-based installer used for VPN client installation and upgrades does
## not have the license.txt in the current directory, intentionally skipping
## the license agreement. Bug CSCtc45589 has been filed for this behavior.
if [ -f "license.txt" ]; then
    cat ./license.txt
    echo
    echo -n "Do you accept the terms in the license agreement? [y/n] "
    read LICENSEAGREEMENT
    while :
    do
      case ${LICENSEAGREEMENT} in
           [Yy][Ee][Ss])
                   echo "You have accepted the license agreement."
                   echo "Please wait while ${CLIENTNAME} is being installed..."
                   break
                   ;;
           [Yy])
                   echo "You have accepted the license agreement."
                   echo "Please wait while ${CLIENTNAME} is being installed..."
                   break
                   ;;
           [Nn][Oo])
                   echo "The installation was cancelled because you did not accept the license agreement."
                   exitInstallation 1
                   ;;
           [Nn])
                   echo "The installation was cancelled because you did not accept the license agreement."
                   exitInstallation 1
                   ;;
           *)
                   echo "Please enter either \"y\" or \"n\"."
                   read LICENSEAGREEMENT
                   ;;
      esac
    done
fi

checkInstalledVersion

checkVersionFeasibilityWithStandaloneNVM

if [ "`basename $0`" != "vpn_install.sh" ]; then
  if which mktemp >/dev/null 2>&1; then
    TEMPDIR=`mktemp -d /tmp/vpn.XXXXXX`
    RMTEMP="yes"
  else
    TEMPDIR="/tmp"
    RMTEMP="no"
  fi
else
  TEMPDIR="."
fi

#
# Check for and uninstall any previous version.
#
if [ -x "${AC_UNINST}" ]; then
  echo "Removing previous installation..."
  echo "Removing previous installation: "${UNINST} >> /tmp/${LOGFNAME}
  STATUS=`${AC_UNINST}`
  if [ "${STATUS}" ]; then
    echo "Error removing previous installation!  Continuing..." >> /tmp/${LOGFNAME}
  fi

elif [ -x "${UNINST}" ]; then
  echo "Removing previous installation..."
  echo "Removing previous installation: "${UNINST} >> /tmp/${LOGFNAME}
  STATUS=`${UNINST}`
  if [ "${STATUS}" ]; then
    echo "Error removing previous installation!  Continuing..." >> /tmp/${LOGFNAME}
  fi
fi

# Data from 4.X version of VPN is NOT migrated when updating from 5.X to 5.Y.
# Otherwise, 4.X data is always migrated to 5.X.
if [ ! -f "%{INSTPREFIX}/update.txt" ]; then
  echo "Migrating ${AC_INSTPREFIX} directory to ${INSTPREFIX} directory"

  mkdir -p ${INSTPREFIX}

  if [ -f "${AC_INSTPREFIX}/AnyConnectLocalPolicy.xml" ] &&
     [ ! -f "${INSTPREFIX}/AnyConnectLocalPolicy.xml" ]; then
    cp -f ${AC_INSTPREFIX}/AnyConnectLocalPolicy.xml ${INSTPREFIX}/ >/dev/null 2>&1
  fi

  if [ -f "${AC_INSTPREFIX}/.anyconnect_global" ] &&
     [ ! -f "${INSTPREFIX}/vpn/.anyconnect_global" ]; then
    mkdir -p ${INSTPREFIX}/vpn
    cp -f ${AC_INSTPREFIX}/.anyconnect_global ${INSTPREFIX}/vpn/ >/dev/null 2>&1
  fi

  if [ -d "${AC_INSTPREFIX}/profile" ]; then
    mkdir -p ${PROFILEDIR}
    tar cf - -C ${AC_INSTPREFIX}/profile . | (cd ${PROFILEDIR}; tar --skip-old-files -x -f -)
  fi

  if [ -d "${AC_INSTPREFIX}/script" ]; then
    mkdir -p ${SCRIPTDIR}
    tar cf - -C ${AC_INSTPREFIX}/script . | (cd ${SCRIPTDIR}; tar --skip-old-files -x -f -)
  fi

  if [ -d "${AC_INSTPREFIX}/l10n" ]; then
    mkdir -p ${INSTPREFIX}/l10n
    tar cf - -C ${AC_INSTPREFIX}/l10n . | (cd ${INSTPREFIX}/l10n; tar --skip-old-files -x -f -)
  fi

  if [ -d "${AC_INSTPREFIX}/help" ]; then
    mkdir -p ${HELPDIR}
    tar cf - -C ${AC_INSTPREFIX}/help . | (cd ${HELPDIR}; tar --skip-old-files -x -f -)
  fi

  if [ -f "${AC_INSTPREFIX}/debuglogconfig.json" ] &&
     [ ! -f "${INSTPREFIX}/debuglogconfig.json" ]; then
    cp -f ${AC_INSTPREFIX}/debuglogconfig.json ${INSTPREFIX}/ >/dev/null 2>&1
  fi

  if [ -f "${AC_INSTPREFIX}/mtuadjustmentcache.json" ] &&
     [ ! -f "${INSTPREFIX}/vpn/mtuadjustmentcache.json" ]; then
    mkdir -p ${INSTPREFIX}/vpn
    cp -f ${AC_INSTPREFIX}/mtuadjustmentcache.json ${INSTPREFIX}/vpn/ >/dev/null 2>&1
  fi
fi

# Ensure that vpn related processes are not running. Uninstall script from older version may leave some of them alive.
OURPROCS=`ps -A -o pid,command | grep -e "${AC_BINDIR}" -e "${BINDIR}" | grep -v 'grep' | awk '{print $1}'`
if [ -n "${OURPROCS}" ] ; then
    for DOOMED in ${OURPROCS}; do
        echo Killing `ps -A -o pid,command -p ${DOOMED} | grep ${DOOMED} | grep -E -v 'ps|grep'` >> /tmp/${LOGFNAME}
        kill -KILL ${DOOMED} >> /tmp/${LOGFNAME} 2>&1
    done
fi

if [ "${TEMPDIR}" != "." ]; then
  TARNAME=`date +%N`
  TARFILE=${TEMPDIR}/vpninst${TARNAME}.tgz

  echo "Extracting installation files to ${TARFILE}..."
  echo "Extracting installation files to ${TARFILE}..." >> /tmp/${LOGFNAME}

  head -n ${MARKER_END} $0 | tail -n +${MARKER} | head -c -1 2>> /tmp/${LOGFNAME} > ${TARFILE} || exitInstallation 1

  echo "Unarchiving installation files to ${TEMPDIR}..."
  echo "Unarchiving installation files to ${TEMPDIR}..." >> /tmp/${LOGFNAME}
  tar xvzf ${TARFILE} -C ${TEMPDIR} >> /tmp/${LOGFNAME} 2>&1 || exitInstallation 1

  rm -f ${TARFILE}

  NEWTEMP="${TEMPDIR}/${TARROOT}"
else
  NEWTEMP="."
fi

# Make sure destination directories exist
echo "Installing "${BINDIR} >> /tmp/${LOGFNAME}
${INSTALL} -d ${BINDIR} || exitInstallation 1
echo "Installing "${LIBDIR} >> /tmp/${LOGFNAME}
${INSTALL} -d ${LIBDIR} || exitInstallation 1
echo "Installing "${PROFILEDIR} >> /tmp/${LOGFNAME}
${INSTALL} -d ${PROFILEDIR} || exitInstallation 1
echo "Installing "${SCRIPTDIR} >> /tmp/${LOGFNAME}
${INSTALL} -d ${SCRIPTDIR} || exitInstallation 1
echo "Installing "${HELPDIR} >> /tmp/${LOGFNAME}
${INSTALL} -d ${HELPDIR} || exitInstallation 1
echo "Installing "${PLUGINDIR} >> /tmp/${LOGFNAME}
${INSTALL} -d ${PLUGINDIR} || exitInstallation 1
echo "Installing "${ROOTCERTSTORE} >> /tmp/${LOGFNAME}
${INSTALL} -d ${ROOTCERTSTORE} || exitInstallation 1
echo "Installing "${AC_INSTPREFIX} >> /tmp/${LOGFNAME}
${INSTALL} -d ${AC_INSTPREFIX} || exitInstallation 1

# Copy files to their home
echo "Installing "${NEWTEMP}/${ROOTCACERT} >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 444 ${NEWTEMP}/${ROOTCACERT} ${ROOTCERTSTORE} || exitInstallation 1

echo "Installing "${NEWTEMP}/${ROOTCACERT_OLD} >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 444 ${NEWTEMP}/${ROOTCACERT_OLD} ${ROOTCERTSTORE} || exitInstallation 1

echo "Installing "${NEWTEMP}/vpn_uninstall.sh >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 755 ${NEWTEMP}/vpn_uninstall.sh ${BINDIR} || exitInstallation 1

echo "Installing "${NEWTEMP}/load_tun.sh >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 755 ${NEWTEMP}/load_tun.sh ${BINDIR} || exitInstallation 1

echo "Installing "${NEWTEMP}/cisco_secure_client_uninstall.sh >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 755 ${NEWTEMP}/cisco_secure_client_uninstall.sh ${BINDIR} || exitInstallation 1

echo "Installing "${NEWTEMP}/vpnagentd >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 755 ${NEWTEMP}/vpnagentd ${BINDIR} || exitInstallation 1

echo "Installing "${NEWTEMP}/libvpnagentutilities.so >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 755 ${NEWTEMP}/libvpnagentutilities.so ${LIBDIR} || exitInstallation 1

echo "Installing "${NEWTEMP}/libvpncommon.so >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 755 ${NEWTEMP}/libvpncommon.so ${LIBDIR} || exitInstallation 1

echo "Installing "${NEWTEMP}/libvpncommoncrypt.so >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 755 ${NEWTEMP}/libvpncommoncrypt.so ${LIBDIR} || exitInstallation 1

echo "Installing "${NEWTEMP}/libvpnapi.so >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 755 ${NEWTEMP}/libvpnapi.so ${LIBDIR} || exitInstallation 1

echo "Installing "${NEWTEMP}/libacruntime.so >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 755 ${NEWTEMP}/libacruntime.so ${LIBDIR} || exitInstallation 1

echo "Installing "${NEWTEMP}/libacciscossl.so >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 755 ${NEWTEMP}/libacciscossl.so ${LIBDIR} || exitInstallation 1

echo "Installing "${NEWTEMP}/libacciscocrypto.so >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 755 ${NEWTEMP}/libacciscocrypto.so ${LIBDIR} || exitInstallation 1

echo "Installing "${NEWTEMP}/cfom.so >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 755 ${NEWTEMP}/cfom.so ${LIBDIR} || exitInstallation 1

echo "Installing "${NEWTEMP}/libaccurl.so.4.8.0 >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 755 ${NEWTEMP}/libaccurl.so.4.8.0 ${LIBDIR} || exitInstallation 1

echo "Creating symlink "${NEWTEMP}/libaccurl.so.4 >> /tmp/${LOGFNAME}
ln -s ${LIBDIR}/libaccurl.so.4.8.0 ${LIBDIR}/libaccurl.so.4 || exitInstallation 1

if [ -f "${NEWTEMP}/libvpnipsec.so" ]; then
    echo "Installing "${NEWTEMP}/libvpnipsec.so >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 755 ${NEWTEMP}/libvpnipsec.so ${PLUGINDIR} || exitInstallation 1
else
    echo "${NEWTEMP}/libvpnipsec.so does not exist. It will not be installed."
fi

if [ -f "${NEWTEMP}/libacfeedback.so" ]; then
    echo "Installing "${NEWTEMP}/libacfeedback.so >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 755 ${NEWTEMP}/libacfeedback.so ${PLUGINDIR} || exitInstallation 1
else
    echo "${NEWTEMP}/libacfeedback.so does not exist. It will not be installed."
fi

if [ -f "${NEWTEMP}/libacwebhelper.so" ]; then
    echo "Installing "${NEWTEMP}/libacwebhelper.so >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 755 ${NEWTEMP}/libacwebhelper.so ${PLUGINDIR} || exitInstallation 1
else
    echo "${NEWTEMP}/libacwebhelper.so does not exist. It will not be installed."
fi

if [ -f "${NEWTEMP}/libboost_date_time.so" ]; then
    echo "Installing "${NEWTEMP}/libboost_date_time.so >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 755 ${NEWTEMP}/libboost_date_time.so ${LIBDIR} || exitInstallation 1
else
    echo "${NEWTEMP}/libboost_date_time.so does not exist. It will not be installed."
fi

if [ -f "${NEWTEMP}/libboost_atomic.so" ]; then
    echo "Installing "${NEWTEMP}/libboost_atomic.so >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 755 ${NEWTEMP}/libboost_atomic.so ${LIBDIR} || exitInstallation 1
else
    echo "${NEWTEMP}/libboost_atomic.so does not exist. It will not be installed."
fi

if [ -f "${NEWTEMP}/libboost_filesystem.so" ]; then
    echo "Installing "${NEWTEMP}/libboost_filesystem.so >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 755 ${NEWTEMP}/libboost_filesystem.so ${LIBDIR} || exitInstallation 1
else
    echo "${NEWTEMP}/libboost_filesystem.so does not exist. It will not be installed."
fi

if [ -f "${NEWTEMP}/libboost_system.so" ]; then
    echo "Installing "${NEWTEMP}/libboost_system.so >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 755 ${NEWTEMP}/libboost_system.so ${LIBDIR} || exitInstallation 1
else
    echo "${NEWTEMP}/libboost_system.so does not exist. It will not be installed."
fi

if [ -f "${NEWTEMP}/libboost_thread.so" ]; then
    echo "Installing "${NEWTEMP}/libboost_thread.so >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 755 ${NEWTEMP}/libboost_thread.so ${LIBDIR} || exitInstallation 1
else
    echo "${NEWTEMP}/libboost_thread.so does not exist. It will not be installed."
fi

if [ -f "${NEWTEMP}/libboost_chrono.so" ]; then
    echo "Installing "${NEWTEMP}/libboost_chrono.so >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 755 ${NEWTEMP}/libboost_chrono.so ${LIBDIR} || exitInstallation 1
else
    echo "${NEWTEMP}/libboost_chrono.so does not exist. It will not be installed."
fi

if [ -f "${NEWTEMP}/libboost_regex.so" ]; then
    echo "Installing "${NEWTEMP}/libboost_regex.so >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 755 ${NEWTEMP}/libboost_regex.so ${LIBDIR} || exit 1
else
    echo "${NEWTEMP}/libboost_regex.so does not exist. It will not be installed."
fi

if [ -f "${NEWTEMP}/vpnui" ]; then
    echo "Installing "${NEWTEMP}/vpnui >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 755 ${NEWTEMP}/vpnui ${BINDIR} || exitInstallation 1
else
    echo "${NEWTEMP}/vpnui does not exist. It will not be installed."
fi

if [ -f "${NEWTEMP}/acwebhelper" ]; then
    echo "Installing "${NEWTEMP}/acwebhelper >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 755 ${NEWTEMP}/acwebhelper ${BINDIR} || exitInstallation 1
else
    echo "${NEWTEMP}/acwebhelper does not exist. It will not be installed."
fi

if [ -f "${NEWTEMP}/acextwebhelper" ]; then
    echo "Installing "${NEWTEMP}/acextwebhelper >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 755 ${NEWTEMP}/acextwebhelper ${BINDIR} || exitInstallation 1
else
    echo "${NEWTEMP}/acextwebhelper does not exist. It will not be installed."
fi

echo "Installing "${NEWTEMP}/vpn >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 755 ${NEWTEMP}/vpn ${BINDIR} || exitInstallation 1

if [ -d "${NEWTEMP}/resources" ]; then
    echo "Copying resources" >> /tmp/${LOGFNAME}
    cp -R ${NEWTEMP}/resources ${INSTPREFIX}
    cp ${NEWTEMP}/resources/vpnui48.png /usr/share/icons/hicolor/48x48/apps/cisco-secure-client.png
    cp ${NEWTEMP}/resources/vpnui64.png /usr/share/icons/hicolor/64x64/apps/cisco-secure-client.png
    cp ${NEWTEMP}/resources/vpnui96.png /usr/share/icons/hicolor/96x96/apps/cisco-secure-client.png
    cp ${NEWTEMP}/resources/vpnui128.png /usr/share/icons/hicolor/128x128/apps/cisco-secure-client.png
    cp ${NEWTEMP}/resources/vpnui256.png /usr/share/icons/hicolor/256x256/apps/cisco-secure-client.png
    cp ${NEWTEMP}/resources/vpnui512.png /usr/share/icons/hicolor/512x512/apps/cisco-secure-client.png >/dev/null 2>&1
else
    echo "resources not found... Installation failed."
    exitInstallation 1
fi

echo "Updating GTK icon cache" >> /tmp/${LOGFNAME}
gtk-update-icon-cache -f -t /usr/share/icons/hicolor >> /tmp/${LOGFNAME} 2>&1

if [ -f "${NEWTEMP}/cisco-secure-client.menu" ]; then
    echo "Installing ${NEWTEMP}/cisco-secure-client.menu" >> /tmp/${LOGFNAME}
    mkdir -p /etc/xdg/menus/applications-merged || exitInstallation
    # there may be an issue where the panel menu doesn't get updated when the applications-merged
    # folder gets created for the first time.
    # This is an ubuntu bug. https://bugs.launchpad.net/ubuntu/+source/gnome-panel/+bug/369405

    ${INSTALL} -o root -m 644 ${NEWTEMP}/cisco-secure-client.menu /etc/xdg/menus/applications-merged/
else
    echo "${NEWTEMP}/cisco-secure-client.menu does not exist. It will not be installed."
fi


if [ -f "${NEWTEMP}/cisco-secure-client.directory" ]; then
    echo "Installing ${NEWTEMP}/cisco-secure-client.directory" >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 644 ${NEWTEMP}/cisco-secure-client.directory /usr/share/desktop-directories/
else
    echo "${NEWTEMP}/cisco-secure-client.directory does not exist. It will not be installed."
fi

# if the update cache utility exists then update the menu cache
# otherwise on some gnome systems, the short cut will disappear
# after user logoff or reboot. This is neccessary on some gnome desktops.
if [ -f "${NEWTEMP}/com.cisco.secureclient.gui.desktop" ]; then
    echo "Installing ${NEWTEMP}/com.cisco.secureclient.gui.desktop" >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 644 ${NEWTEMP}/com.cisco.secureclient.gui.desktop /usr/share/applications/
    if [ -x "/usr/share/gnome-menus/update-gnome-menus-cache" ]; then
        for CACHE_FILE in $(ls /usr/share/applications/desktop.*.cache); do
            echo "updating ${CACHE_FILE}" >> /tmp/${LOGFNAME}
            /usr/share/gnome-menus/update-gnome-menus-cache /usr/share/applications/ > ${CACHE_FILE}
        done
    fi
else
    echo "${NEWTEMP}/com.cisco.secureclient.gui.desktop does not exist. It will not be installed."
fi

if [ -f "${NEWTEMP}/ACManifestVPN.xml" ]; then
    echo "Installing "${NEWTEMP}/ACManifestVPN.xml" at ${INSTPREFIX}">> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 444 ${NEWTEMP}/ACManifestVPN.xml ${INSTPREFIX} || exitInstallation 1
    
    # Creating symlink to prevent installation of older versions.
    echo "Creating ACManifestVPN.xml symlink at ${AC_INSTPREFIX}">> /tmp/${LOGFNAME}
    ln -f -s ${INSTPREFIX}/ACManifestVPN.xml ${AC_INSTPREFIX}/ACManifestVPN.xml
else
    echo "${NEWTEMP}/ACManifestVPN.xml does not exist. It will not be installed."
fi

if [ -f "${NEWTEMP}/manifesttool_vpn" ]; then
    echo "Installing "${NEWTEMP}/manifesttool_vpn >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 755 ${NEWTEMP}/manifesttool_vpn ${BINDIR} || exitInstallation 1

    # create symlinks for legacy install compatibility
    echo "Creating manifesttool symlink for legacy install compatibility." >> /tmp/${LOGFNAME}
    ln -f -s ${BINDIR}/manifesttool_vpn ${BINDIR}/manifesttool
else
    echo "${NEWTEMP}/manifesttool_vpn does not exist. It will not be installed."
fi


if [ -f "${NEWTEMP}/update.txt" ]; then
    echo "Installing "${NEWTEMP}/update.txt >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 444 ${NEWTEMP}/update.txt ${INSTPREFIX} || exitInstallation 1
else
    echo "${NEWTEMP}/update.txt does not exist. It will not be installed."
fi


if [ -f "${NEWTEMP}/vpndownloader" ]; then
    # cached downloader
    echo "Installing "${NEWTEMP}/vpndownloader >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 755 ${NEWTEMP}/vpndownloader ${BINDIR} || exitInstallation 1
else
    echo "${NEWTEMP}/vpndownloader does not exist. It will not be installed."
fi

if [ -f "${NEWTEMP}/vpndownloader-cli" ]; then
    # cached downloader (cli)
    echo "Installing "${NEWTEMP}/vpndownloader-cli >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 755 ${NEWTEMP}/vpndownloader-cli ${BINDIR} || exitInstallation 1
else
    echo "${NEWTEMP}/vpndownloader-cli does not exist. It will not be installed."
fi

if [ -f "${NEWTEMP}/libacdownloader.so" ]; then
    echo "Installing "${NEWTEMP}/libacdownloader.so >> /tmp/${LOGFNAME}
    ${INSTALL} -o root -m 755 ${NEWTEMP}/libacdownloader.so ${PLUGINDIR} || exit 1
else
    echo "${NEWTEMP}/libacdownloader.so does not exist. It will not be installed."
fi

echo "Installing "${NEWTEMP}/acinstallhelper >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 755 ${NEWTEMP}/acinstallhelper ${BINDIR} || exitInstallation 1


# Open source information
echo "Installing "${NEWTEMP}/OpenSource.html >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 444 ${NEWTEMP}/OpenSource.html ${INSTPREFIX} || exitInstallation 1

# Profile schema
echo "Installing "${NEWTEMP}/AnyConnectProfile.xsd >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 444 ${NEWTEMP}/AnyConnectProfile.xsd ${PROFILEDIR} || exitInstallation 1

echo "Installing "${NEWTEMP}/AnyConnectLocalPolicy.xsd >> /tmp/${LOGFNAME}
${INSTALL} -o root -m 444 ${NEWTEMP}/AnyConnectLocalPolicy.xsd ${INSTPREFIX} || exitInstallation 1

# Import any Cisco Secure Client XML profiles and read the ACTransforms.xml
# Errors that occur during import are intentionally ignored (best effort)

INSTALLER_FILE_DIR=$(dirname "$0")

IS_PRE_DEPLOY=true

if [ "${TEMPDIR}" != "." ]; then
    IS_PRE_DEPLOY=false;
fi

if $IS_PRE_DEPLOY; then
  PROFILE_IMPORT_DIR="${INSTALLER_FILE_DIR}/../Profiles"
  VPN_PROFILE_IMPORT_DIR="${INSTALLER_FILE_DIR}/../Profiles/vpn"

  if [ -d ${PROFILE_IMPORT_DIR} ]; then
    find ${PROFILE_IMPORT_DIR} -maxdepth 1 -name "AnyConnectLocalPolicy.xml" -type f -exec ${INSTALL} -o root -m 644 {} ${INSTPREFIX} \;
  fi

  if [ -d ${VPN_PROFILE_IMPORT_DIR} ]; then
    find ${VPN_PROFILE_IMPORT_DIR} -maxdepth 1 -name "*.xml" -type f -exec ${INSTALL} -o root -m 644 {} ${PROFILEDIR} \;
  fi
fi

# Process transforms
# API to get the value of the tag from the transforms file
# The Third argument will be used to check if the tag value needs to converted to lowercase
getProperty()
{
    FILE=${1}
    TAG=${2}
    TAG_FROM_FILE=$(grep ${TAG} "${FILE}" | sed "s/\(.*\)\(<${TAG}>\)\(.*\)\(<\/${TAG}>\)\(.*\)/\3/")
    if [ "${3}" = "true" ]; then
        TAG_FROM_FILE=`echo ${TAG_FROM_FILE} | tr '[:upper:]' '[:lower:]'`
    fi
    echo $TAG_FROM_FILE;
}

DISABLE_VPN_TAG="DisableVPN"
DISABLE_FEEDBACK_TAG="DisableCustomerExperienceFeedback"

BYPASS_DOWNLOADER_TAG="BypassDownloader"
BYPASS_DEFAULT_LOCALIZATION_TAG="BypassDefaultLocalization"
RESTRICT_SCRIPT_WEBDEPLOY_TAG="RestrictScriptWebDeploy"
RESTRICT_HELP_WEBDEPLOY_TAG="RestrictHelpWebDeploy"
RESTRICT_RESOURCE_WEBDEPLOY_TAG="RestrictResourceWebDeploy"
RESTRICT_LOCALIZATION_WEBDEPLOY_TAG="RestrictLocalizationWebDeploy"
FIPS_MODE_TAG="FipsMode"
RESTRICT_PREFERENCE_CACHING_TAG="RestrictPreferenceCaching"
RESTRICT_TUNNEL_PROTOCOLS_TAG="RestrictTunnelProtocols"
RESTRICT_WEB_LAUNCH_TAG="RestrictWebLaunch"
STRICT_CERTIFICATE_TRUST_TAG="StrictCertificateTrust"
EXCLUDE_FIREFOX_NSS_CERT_STORE_TAG="ExcludeFirefoxNSSCertStore"
ALLOW_SOFTWARE_UPDATES_FROM_ANY_SERVER_TAG="AllowSoftwareUpdatesFromAnyServer"
ALLOW_COMPLIANCE_MODULE_UPDATES_FROM_ANY_SERVER_TAG="AllowComplianceModuleUpdatesFromAnyServer"
ALLOW_VPN_PROFILE_UPDATES_FROM_ANY_SERVER_TAG="AllowVPNProfileUpdatesFromAnyServer"
ALLOW_MGMT_VPN_PROFILE_UPDATES_FROM_ANY_SERVER_TAG="AllowManagementVPNProfileUpdatesFromAnyServer"
ALLOW_ISE_PROFILE_UPDATES_FROM_ANY_SERVER_TAG="AllowISEProfileUpdatesFromAnyServer"
ALLOW_SERVICE_PROFILE_UPDATES_FROM_ANY_SERVER_TAG="AllowServiceProfileUpdatesFromAnyServer"
ALLOW_SCRIPT_UPDATES_FROM_ANY_SERVER_TAG="AllowScriptUpdatesFromAnyServer"
ALLOW_HELP_UPDATES_FROM_ANY_SERVER_TAG="AllowHelpUpdatesFromAnyServer"
ALLOW_RESOURCE_UPDATES_FROM_ANY_SERVER_TAG="AllowResourceUpdatesFromAnyServer"
ALLOW_LOCALIZATION_UPDATES_FROM_ANY_SERVER_TAG="AllowLocalizationUpdatesFromAnyServer"
AUTHORIZED_SERVER_LIST_TAG="AuthorizedServerList"
RESTRICT_SERVER_CERT_STORE_TAG="RestrictServerCertStore"
OCSP_REVOCATION_TAG="OCSPRevocation"

if $IS_PRE_DEPLOY; then
    if [ -d "${PROFILE_IMPORT_DIR}" ]; then
        TRANSFORM_FILE="${PROFILE_IMPORT_DIR}/ACTransforms.xml"
    fi
else
    TRANSFORM_FILE="${INSTALLER_FILE_DIR}/ACTransforms.xml"
fi

if [ -f "${TRANSFORM_FILE}" ] ; then
    echo "Processing transform file in ${TRANSFORM_FILE}"
    DISABLE_VPN=$(getProperty "${TRANSFORM_FILE}" ${DISABLE_VPN_TAG})
    DISABLE_FEEDBACK=$(getProperty "${TRANSFORM_FILE}" ${DISABLE_FEEDBACK_TAG} "true" )

    BYPASS_DOWNLOADER=$(getProperty "${TRANSFORM_FILE}" ${BYPASS_DOWNLOADER_TAG})
    BYPASS_DEFAULT_LOCALIZATION=$(getProperty "${TRANSFORM_FILE}" ${BYPASS_DEFAULT_LOCALIZATION_TAG})
    RESTRICT_SCRIPT_WEBDEPLOY=$(getProperty "${TRANSFORM_FILE}" ${RESTRICT_SCRIPT_WEBDEPLOY_TAG})
    RESTRICT_HELP_WEBDEPLOY=$(getProperty "${TRANSFORM_FILE}" ${RESTRICT_HELP_WEBDEPLOY_TAG})
    RESTRICT_RESOURCE_WEBDEPLOY=$(getProperty "${TRANSFORM_FILE}" ${RESTRICT_RESOURCE_WEBDEPLOY_TAG})
    RESTRICT_LOCALIZATION_WEBDEPLOY=$(getProperty "${TRANSFORM_FILE}" ${RESTRICT_LOCALIZATION_WEBDEPLOY_TAG})
    FIPS_MODE=$(getProperty "${TRANSFORM_FILE}" ${FIPS_MODE_TAG})
    RESTRICT_PREFERENCE_CACHING=$(getProperty "${TRANSFORM_FILE}" ${RESTRICT_PREFERENCE_CACHING_TAG})
    RESTRICT_TUNNEL_PROTOCOLS=$(getProperty "${TRANSFORM_FILE}" ${RESTRICT_TUNNEL_PROTOCOLS_TAG})
    RESTRICT_WEB_LAUNCH=$(getProperty "${TRANSFORM_FILE}" ${RESTRICT_WEB_LAUNCH_TAG})
    STRICT_CERTIFICATE_TRUST=$(getProperty "${TRANSFORM_FILE}" ${STRICT_CERTIFICATE_TRUST_TAG})
    EXCLUDE_FIREFOX_NSS_CERT_STORE=$(getProperty "${TRANSFORM_FILE}" ${EXCLUDE_FIREFOX_NSS_CERT_STORE_TAG})
    ALLOW_SOFTWARE_UPDATES_FROM_ANY_SERVER=$(getProperty "${TRANSFORM_FILE}" ${ALLOW_SOFTWARE_UPDATES_FROM_ANY_SERVER_TAG})
    ALLOW_COMPLIANCE_MODULE_UPDATES_FROM_ANY_SERVER=$(getProperty "${TRANSFORM_FILE}" ${ALLOW_COMPLIANCE_MODULE_UPDATES_FROM_ANY_SERVER_TAG})
    ALLOW_VPN_PROFILE_UPDATES_FROM_ANY_SERVER=$(getProperty "${TRANSFORM_FILE}" ${ALLOW_VPN_PROFILE_UPDATES_FROM_ANY_SERVER_TAG})
    ALLOW_MGMT_VPN_PROFILE_UPDATES_FROM_ANY_SERVER=$(getProperty "${TRANSFORM_FILE}" ${ALLOW_MGMT_VPN_PROFILE_UPDATES_FROM_ANY_SERVER_TAG})
    ALLOW_ISE_PROFILE_UPDATES_FROM_ANY_SERVER=$(getProperty "${TRANSFORM_FILE}" ${ALLOW_ISE_PROFILE_UPDATES_FROM_ANY_SERVER_TAG})
    ALLOW_SERVICE_PROFILE_UPDATES_FROM_ANY_SERVER=$(getProperty "${TRANSFORM_FILE}" ${ALLOW_SERVICE_PROFILE_UPDATES_FROM_ANY_SERVER_TAG})
    ALLOW_SCRIPT_UPDATES_FROM_ANY_SERVER=$(getProperty "${TRANSFORM_FILE}" ${ALLOW_SCRIPT_UPDATES_FROM_ANY_SERVER_TAG})
    ALLOW_HELP_UPDATES_FROM_ANY_SERVER=$(getProperty "${TRANSFORM_FILE}" ${ALLOW_HELP_UPDATES_FROM_ANY_SERVER_TAG})
    ALLOW_RESOURCE_UPDATES_FROM_ANY_SERVER=$(getProperty "${TRANSFORM_FILE}" ${ALLOW_RESOURCE_UPDATES_FROM_ANY_SERVER_TAG})
    ALLOW_LOCALIZATION_UPDATES_FROM_ANY_SERVER=$(getProperty "${TRANSFORM_FILE}" ${ALLOW_LOCALIZATION_UPDATES_FROM_ANY_SERVER_TAG})
    AUTHORIZED_SERVER_LIST=$(getProperty "${TRANSFORM_FILE}" ${AUTHORIZED_SERVER_LIST_TAG})
    RESTRICT_SERVER_CERT_STORE=$(getProperty "${TRANSFORM_FILE}" ${RESTRICT_SERVER_CERT_STORE_TAG})
    OCSP_REVOCATION=$(getProperty "${TRANSFORM_FILE}" ${OCSP_REVOCATION_TAG})
fi

# if disable phone home is specified, remove the phone home plugin and any data folder
# note: this will remove the customer feedback profile if it was imported above
FEEDBACK_PLUGIN="${PLUGINDIR}/libacfeedback.so"

if [ "x${DISABLE_FEEDBACK}" = "xtrue" ] ; then
    echo "Disabling Customer Experience Feedback plugin"
    rm -f ${FEEDBACK_PLUGIN}
    rm -rf ${FEEDBACK_DIR}
fi

# generate default AnyConnectLocalPolicy.xml if it doesn't already exist
${BINDIR}/acinstallhelper -acpolgen bd=${BYPASS_DOWNLOADER:-false} \
                                    bdl=${BYPASS_DEFAULT_LOCALIZATION:-false} \
                                    rswd=${RESTRICT_SCRIPT_WEBDEPLOY:-false} \
                                    rhwd=${RESTRICT_HELP_WEBDEPLOY:-false} \
                                    rrwd=${RESTRICT_RESOURCE_WEBDEPLOY:-false} \
                                    rlwd=${RESTRICT_LOCALIZATION_WEBDEPLOY:-false} \
                                    fm=${FIPS_MODE:-false} \
                                    rpc=${RESTRICT_PREFERENCE_CACHING:-false} \
                                    rtp=${RESTRICT_TUNNEL_PROTOCOLS:-false} \
                                    rwl=${RESTRICT_WEB_LAUNCH:-false} \
                                    sct=${STRICT_CERTIFICATE_TRUST:-false} \
                                    efn=${EXCLUDE_FIREFOX_NSS_CERT_STORE:-false} \
                                    upsu=${ALLOW_SOFTWARE_UPDATES_FROM_ANY_SERVER:-true} \
                                    upcu=${ALLOW_COMPLIANCE_MODULE_UPDATES_FROM_ANY_SERVER:-true} \
                                    upvp=${ALLOW_VPN_PROFILE_UPDATES_FROM_ANY_SERVER:-true} \
                                    upmv=${ALLOW_MGMT_VPN_PROFILE_UPDATES_FROM_ANY_SERVER:-true} \
                                    upip=${ALLOW_ISE_PROFILE_UPDATES_FROM_ANY_SERVER:-true} \
                                    upsp=${ALLOW_SERVICE_PROFILE_UPDATES_FROM_ANY_SERVER:-true} \
                                    upscr=${ALLOW_SCRIPT_UPDATES_FROM_ANY_SERVER:-true} \
                                    uphlp=${ALLOW_HELP_UPDATES_FROM_ANY_SERVER:-true} \
                                    upres=${ALLOW_RESOURCE_UPDATES_FROM_ANY_SERVER:-true} \
                                    uploc=${ALLOW_LOCALIZATION_UPDATES_FROM_ANY_SERVER:-true} \
                                    upal=${AUTHORIZED_SERVER_LIST} \
                                    rsc=${RESTRICT_SERVER_CERT_STORE:-false} \
                                    orc=${OCSP_REVOCATION:-false}

if [ -x ${NVMUNINSTALLSCRIPT} ] && [ ! -e "${PLUGINDIR}/libacnvmctrl.so" ] ; then
  # uninstall standalone nvm and cache the config files for restoration
  ${NVMUNINSTALLSCRIPT} -saveconfig
  if [ "$?" -ne "0" ]; then
      echo "Error removing Standalone NVM"
      echo "Error removing Standalone NVM" >> /tmp/${LOGFNAME}
  fi
fi

TESTINIT=`ls -l /proc/1/exe`
if [ -z "${TESTINIT##*"systemd"*}" ]; then
  echo systemctl daemon-reexec >> /tmp/${LOGFNAME}
  systemctl daemon-reexec >> /tmp/${LOGFNAME} 2>&1
  # try stop vpnagentd service first in case user is upgrading from old version which doesn't have the proper unintall script
  echo systemctl stop ${SYSTEMD_CONF} >> /tmp/${LOGFNAME}
  systemctl stop ${SYSTEMD_CONF} >> /tmp/${LOGFNAME} 2>&1
  echo systemctl disable ${SYSTEMD_CONF} >> /tmp/${LOGFNAME}
  systemctl disable ${SYSTEMD_CONF} >> /tmp/${LOGFNAME} 2>&1

  echo "install systemd config" >> /tmp/${LOGFNAME}
  echo "Installing "${NEWTEMP}/${SYSTEMD_CONF} >> /tmp/${LOGFNAME}
  echo ${INSTALL} -o root -m 644 ${NEWTEMP}/${SYSTEMD_CONF} ${SYSTEMD_CONF_DIR}/${SYSTEMD_CONF} >> /tmp/${LOGFNAME}
  ${INSTALL} -o root -m 644 ${NEWTEMP}/${SYSTEMD_CONF} ${SYSTEMD_CONF_DIR}/${SYSTEMD_CONF} || exitInstallation 1

  echo systemctl enable ${SYSTEMD_CONF} >> /tmp/${LOGFNAME}
  systemctl enable ${SYSTEMD_CONF} >> /tmp/${LOGFNAME} 2>&1

  echo "Starting ${CLIENTNAME} Agent..."
  echo "Starting ${CLIENTNAME} Agent..." >> /tmp/${LOGFNAME}

  echo systemctl start ${SYSTEMD_CONF} >> /tmp/${LOGFNAME}
  systemctl start ${SYSTEMD_CONF} >> /tmp/${LOGFNAME} 2>&1 || exitInstallation 1
else
  echo "Error: systemd required." >> /tmp/${LOGFNAME} || exitInstallation 1
fi

# Generate/update the VPNManifest.dat file
if [ -f ${BINDIR}/manifesttool_vpn ]; then  
  ${BINDIR}/manifesttool_vpn -i ${INSTPREFIX} ${INSTPREFIX}/ACManifestVPN.xml
fi


if [ "${RMTEMP}" = "yes" ]; then
  echo rm -rf ${TEMPDIR} >> /tmp/${LOGFNAME}
  rm -rf ${TEMPDIR}
fi

echo "Done!"
echo "Done!" >> /tmp/${LOGFNAME}

exitInstallation 0

--BEGIN ARCHIVE--
