#!/usr/bin/python

import json
import logging
import socket
import sys
import urllib2
import urllib


class LogicMonitor(object):

    def __init__(self, module, **params):
        self.__version__ = "1.0-python"
        logging.debug("Instantiating LogicMonitor object")

        self.check_mode = False
        self.company = params["company"]
        self.user = params["user"]
        self.password = params["password"]
        self.fqdn = socket.getfqdn()
        self.lm_url = "logicmonitor.com/santaba"

        # Grab the Ansible module if provided
        try:
            self.module = module
            self.urlopen = open_url  # use the ansible provided open_url
            self.__version__ = self.__version__ + "-ansible-module"
            logging.basicConfig(level=logging.DEBUG)
        except:
            self.module = None
            self.urlopen = urllib2.urlopen

    def rpc(self, action, params):
        """Make a call to the LogicMonitor RPC library
        and return the response"""
        logging.debug("Running LogicMonitor.rpc")

        param_str = urllib.urlencode(params)
        creds = urllib.urlencode(
            {"c": self.company,
                "u": self.user,
                "p": self.password})

        if param_str:
            param_str = param_str + "&"

        param_str = param_str + creds

        try:
            url = ("https://{0}.{1}/rpc/{2}?{3}"
                   .format(self.company, self.lm_url, action, param_str))

            # Set custom LogicMonitor header with version
            headers = {"X-LM-User-Agent": self.__version__}

            # Set headers dependent on Ansible or normal usage
            if self.module is not None:
                f = self.urlopen(url, headers=headers)
            else:
                req = urllib2.Request(url)
                req.add_header("X-LM-User-Agent", self.__version__)
                f = self.urlopen(req)

            raw = f.read()
            resp = json.loads(raw)
            if resp["status"] == 403:
                logging.debug("Authentication failed.")
                self.fail(msg="Error: {0}".format(resp["errmsg"]))
            else:
                return raw
        except IOError, ioe:
            logging.debug(ioe)
            self.fail(msg="Error: Unknown exception making RPC call")

    def do(self, action, params):
        """Make a call to the LogicMonitor
         server \"do\" function"""
        logging.debug("Running LogicMonitor.do...")

        param_str = urllib.urlencode(params)
        creds = (urllib.urlencode(
            {"c": self.company,
                "u": self.user,
                "p": self.password}))

        if param_str:
            param_str = param_str + "&"
        param_str = param_str + creds

        try:
            logging.debug("Attempting to open URL: " +
                          "https://{0}.{1}/do/{2}?{3}"
                          .format(self.company,
                                  self.lm_url,
                                  action,
                                  param_str))
            f = self.urlopen(
                "https://{0}.{1}/do/{2}?{3}"
                .format(self.company, self.lm_url, action, param_str))
            return f.read()
        except IOError, ioe:
            logging.debug("Error opening URL. {0}".format(ioe))
            self.fail("Unknown exception opening URL")

    def get_collectors(self):
        """Returns a JSON object containing a list of
        LogicMonitor collectors"""
        logging.debug("Running LogicMonitor.get_collectors...")

        logging.debug("Making RPC call to 'getAgents'")
        resp = self.rpc("getAgents", {})
        resp_json = json.loads(resp)

        if resp_json["status"] is 200:
            logging.debug("RPC call succeeded")
            return resp_json["data"]
        else:
            self.fail(msg=resp)

    def get_host_by_hostname(self, hostname, collector):
        """Returns a host object for the host matching the
        specified hostname"""
        logging.debug("Running LogicMonitor.get_host_by_hostname...")

        logging.debug("Looking for hostname {0}".format(hostname))
        logging.debug("Making RPC call to 'getHosts'")
        hostlist_json = json.loads(self.rpc("getHosts", {"hostGroupId": 1}))

        if collector:
            if hostlist_json["status"] == 200:
                logging.debug("RPC call succeeded")

                hosts = hostlist_json["data"]["hosts"]

                logging.debug(
                    "Looking for host matching: hostname {0} and collector {1}"
                    .format(hostname, collector["id"]))

                for host in hosts:
                    if (host["hostName"] == hostname and
                       host["agentId"] == collector["id"]):

                        logging.debug("Host match found")
                        return host
                logging.debug("No host match found")
                return None
            else:
                logging.debug("RPC call failed")
                logging.debug(hostlist_json)
        else:
            logging.debug("No collector specified")
            return None

    def get_host_by_displayname(self, displayname):
        """Returns a host object for the host matching the
        specified display name"""
        logging.debug("Running LogicMonitor.get_host_by_displayname...")

        logging.debug("Looking for displayname {0}".format(displayname))
        logging.debug("Making RPC call to 'getHost'")
        host_json = (json.loads(self.rpc("getHost",
                                {"displayName": displayname})))

        if host_json["status"] == 200:
            logging.debug("RPC call succeeded")
            return host_json["data"]
        else:
            logging.debug("RPC call failed")
            logging.debug(host_json)
            return None

    def get_collector_by_description(self, description):
        """Returns a JSON collector object for the collector
        matching the specified FQDN (description)"""
        logging.debug("Running LogicMonitor.get_collector_by_description...")

        collector_list = self.get_collectors()
        if collector_list is not None:
            logging.debug("Looking for collector with description {0}"
                          .format(description))
            for collector in collector_list:
                if collector["description"] == description:
                    logging.debug("Collector match found")
                    return collector
        logging.debug("No collector match found")
        return None

    def get_group(self, fullpath):
        """Returns a JSON group object for the group matching the
        specified path"""
        logging.debug("Running LogicMonitor.get_group...")

        logging.debug("Making RPC call to getHostGroups")
        resp = json.loads(self.rpc("getHostGroups", {}))

        if resp["status"] == 200:
            logging.debug("RPC called succeeded")
            groups = resp["data"]

            logging.debug("Looking for group matching {0}".format(fullpath))
            for group in groups:
                if group["fullPath"] == fullpath.lstrip('/'):
                    logging.debug("Group match found")
                    return group

            logging.debug("No group match found")
            return None
        else:
            logging.debug("RPC call failed")
            logging.debug(resp)

        return None

    def create_group(self, fullpath):
        """Recursively create a path of host groups.
        Returns the id of the newly created hostgroup"""
        logging.debug("Running LogicMonitor.create_group...")

        res = self.get_group(fullpath)
        if res:
            logging.debug("Group {0} exists.".format(fullpath))
            return res["id"]

        if fullpath == "/":
            logging.debug("Specified group is root. Doing nothing.")
            return 1
        else:
            logging.debug("Creating group named {0}".format(fullpath))
            logging.debug("System changed")
            self.change = True

            if self.check_mode:
                self.exit(changed=True)

            parentpath, name = fullpath.rsplit('/', 1)
            parentgroup = self.get_group(parentpath)

            parentid = 1

            if parentpath == "":
                parentid = 1
            elif parentgroup:
                parentid = parentgroup["id"]
            else:
                parentid = self.create_group(parentpath)

            h = None

            # Determine if we're creating a group from host or hostgroup class
            if hasattr(self, '_build_host_group_hash'):
                h = self._build_host_group_hash(
                    fullpath,
                    self.description,
                    self.properties,
                    self.alertenable)
                h["name"] = name
                h["parentId"] = parentid
            else:
                h = {"name": name,
                     "parentId": parentid,
                     "alertEnable": True,
                     "description": ""}

            logging.debug("Making RPC call to 'addHostGroup'")
            resp = json.loads(
                self.rpc("addHostGroup", h))

            if resp["status"] == 200:
                logging.debug("RPC call succeeded")
                return resp["data"]["id"]
            elif resp["errmsg"] == "The record already exists":
                logging.debug("The hostgroup already exists")
                group = self.get_group(fullpath)
                return group["id"]
            else:
                logging.debug("RPC call failed")
                self.fail(
                    msg="Error: unable to create new hostgroup \"{0}\".\n{1}"
                    .format(name, resp["errmsg"]))

    def fail(self, msg):
        logging.warning(msg)

        # Use Ansible module functions if provided
        try:
            self.module.fail_json(msg=msg, changed=self.change, failed=True)
        except:
            print(msg)
            sys.exit(1)

    def exit(self, changed):
        print("Changed: {0}".format(changed))

        # Use Ansible module functions if provided
        try:
            self.module.exit_json(changed=changed, success=True)
        except:
            print("Changed: {0}".format(changed))
            sys.exit(0)

    def output_info(self, info):
        try:
            logging.debug("Registering properties as Ansible facts")
            self.module.exit_json(changed=False, ansible_facts=info)
        except:
            print("Properties: {0}".format(info))
