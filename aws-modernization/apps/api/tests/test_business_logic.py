"""Business logic read from the C# syntax tree, and its wording in user stories.

The controller below has the shape of the real IMS `InvoiceApiController.Post` (submit an invoice): every business
rule of it must reach the story, with its conditions and its exact outcome.
"""
from __future__ import annotations

import pytest

from app import business_logic, user_stories

pytest.importorskip("tree_sitter_c_sharp")
sts = user_stories.sts
ct = sts.ct

INVOICE_API = '''
public class InvoiceApiController : ApiController
{
    public HttpResponseMessage Post(InvoiceModel model)
    {
        try
        {
            model.StatusId = GetInvoiceStatusId("Pending");
            var particularPremium = model.Particulars.First();
            particularPremium.ParticularTypeId = GetParticularTypeId("Premium");
            if (model.Particulars.Count > 1)
            {
                var particularVAT = model.Particulars[1];
                if (particularVAT.ParticularTypeId == 0)
                    particularVAT.ParticularTypeId = GetParticularTypeId("Value-Added Tax (VAT)");
            }
            var entity = AutoMapper.Mapper.Map<Invoice>(model);
            if (entity.Id == 0)
            {
                entity.PaidDate = new DateTime(1900, 01, 01);
                if (CreateNewInvoice(entity) == false)
                    return Request.CreateResponse(HttpStatusCode.BadRequest, new { error = "InvoiceNumber" });
            }
            else
            {
                if (SaveModifications(entity) == false)
                    return Request.CreateResponse(HttpStatusCode.BadRequest, new { error = "InvoiceNumber" });
            }
            var clientName = client.LastName + ", " + client.FirstName;
            var policyNumber = Uow.Policies.GetById(model.PolicyId).PolicyNumber;
            _emailSvc.SendNeedApprovalInvoice(model, clientName, policyNumber);
            return Request.CreateResponse(HttpStatusCode.OK);
        }
        catch (Exception ex)
        {
            return Request.CreateResponse(HttpStatusCode.BadRequest);
        }
    }

    private bool CreateNewInvoice(Invoice entity)
    {
        if (CheckIfInvoiceNumberExists(entity))
            return false;
        Uow.Invoices.Add(entity);
        Uow.SaveChanges();
        LogAdd(entity);
        return true;
    }

    private bool CheckIfInvoiceNumberExists(Invoice entity)
    {
        var policy = Uow.Policies.GetById(entity.PolicyId);
        var count = Uow.Invoices.GetAll()
            .Where(i => i.InvoiceNumber == entity.InvoiceNumber &&
                    i.Policy.InsuranceProviderId == policy.InsuranceProviderId)
            .Count();
        return count != 0;
    }

    private bool CheckIfDuplicateInvoiceNumber(Invoice entity)
    {
        bool ret = false;
        var invoices = Uow.Invoices.GetAll()
            .Where(i => i.InvoiceNumber == entity.InvoiceNumber &&
                    i.Policy.InsuranceProviderId == policy.InsuranceProviderId)
            .ToList();
        if (invoices.Count() != 0)
        {
            if (invoices[0].Id != entity.Id)
                ret = true;
        }
        return ret;
    }

    private bool SaveModifications(Invoice entity)
    {
        if (CheckIfDuplicateInvoiceNumber(entity))
            return false;
        var pIdList = Uow.Particulars.GetAll().Where(p => p.InvoiceId == entity.Id).Select(p => p.Id).ToList();
        foreach (var item in entity.Particulars)
        {
            if (item.Id == 0)
            {
                item.InvoiceId = entity.Id;
                Uow.Particulars.Add(item);
            }
            else
            {
                Uow.Particulars.Update(item);
                pIdList.Remove(item.Id);
            }
        }
        foreach (var item in pIdList)
        {
            Uow.Particulars.Delete(item);
        }
        Uow.Invoices.Update(entity);
        Uow.SaveChanges();
        return true;
    }

    private int GetInvoiceStatusId(string value) { return Uow.InvoiceStatuses.GetAll().First(s => s.Name == value).Id; }
    private int GetParticularTypeId(string value) { return Uow.ParticularTypes.GetAll().First(p => p.Name == value).Id; }
}
'''

FILE = "App/Controllers/InvoiceApiController.cs"
OWNER = "App.Controllers.InvoiceApiController"


def _steps(*calls: tuple[str, str, int]) -> list[dict]:
    return [{"from": f"{OWNER}.{a}", "kind": "CALLS", "to": f"{OWNER}.{b}", "file": FILE, "line": line}
            for a, b, line in calls]


POST_STEPS = _steps(("Post", "GetInvoiceStatusId", 8), ("Post", "CreateNewInvoice", 20), ("Post", "SaveModifications", 25),
                    ("CreateNewInvoice", "CheckIfInvoiceNumberExists", 39), ("SaveModifications",
                                                                              "CheckIfDuplicateInvoiceNumber", 75))


def _analyse(source: str = INVOICE_API, entry: str = "Post", steps: list[dict] | None = None) -> dict:
    lines = source.splitlines()
    return business_logic.analyse(f"{OWNER}.{entry}", steps or POST_STEPS, lambda rel: lines if rel == FILE else [])


def _worded(out: dict, noun: str = "invoice") -> list[str]:
    result = []
    for r in out["rules"]:
        ctx = ct.Ctx(noun, out["aliases"], out["helpers"], r["method"], out["entry"])
        t = ct.logic_rule(r, ctx)
        result.append((f"if {' and '.join(t['given'])}, " if t["given"] else "") + " and ".join(t["then"]))
    return result


def test_every_business_rule_of_submit_invoice_is_found_and_worded():
    out = _analyse()
    assert _worded(out) == [
        'the status is set to "Pending" and the particular type of the first particular (premium) is set to "Premium"',
        'if there is more than 1 particular and the particular type of the second particular (VAT) is not set, '
        'the particular type of the second particular (VAT) is set to "Value-Added Tax (VAT)"',
        "if the invoice has not been saved yet, the paid date is set to 1 January 1900",
        "if the invoice has not been saved yet and an invoice with the same invoice number and the same insurance "
        'provider already exists, the request is refused with the error "InvoiceNumber"',
        "if the invoice has been saved before and another invoice with the same invoice number and the same "
        'insurance provider already exists, the request is refused with the error "InvoiceNumber"',
        'a "need approval invoice" email is sent with the client name and the policy number',
        "if anything goes wrong, the request is refused",
        "if the invoice has not been saved yet and no invoice with the same invoice number and the same insurance "
        "provider exists, the invoice is added",
        "if the invoice has been saved before and no other invoice with the same invoice number and the same "
        "insurance provider exists, each particular of the invoice that has not been saved yet is added",
        "if the invoice has been saved before and no other invoice with the same invoice number and the same "
        "insurance provider exists, each particular of the invoice that has been saved before is updated",
        "if the invoice has been saved before and no other invoice with the same invoice number and the same "
        "insurance provider exists, each particular already saved for the invoice that is no longer in it is deleted",
        "if the invoice has been saved before and no other invoice with the same invoice number and the same "
        "insurance provider exists, the invoice is updated",
    ]


def test_rules_are_anchored_and_technical_steps_are_left_out():
    out = _analyse()
    first = out["rules"][0]
    assert (first["method"], first["file"], first["line"]) == ("Post", FILE, 8)
    assert 'GetInvoiceStatusId("Pending")' in first["snippets"][0]
    actions = [a for r in out["rules"] for a in r["then"]]
    assert not [a for a in actions if "SaveChanges" in str(a) or "LogAdd" in str(a)], "plumbing is not a rule"
    assert not [a for a in actions if a["type"] == "set" and a["target"] == "item.InvoiceId"], \
        "linking a record to its parent by id is not a business rule"
    assert out["helpers"]["CreateNewInvoice"]["failsWhen"] == [[{"code": "CheckIfInvoiceNumberExists(entity)",
                                                                  "negated": False}]]
    assert "i.InvoiceNumber == entity.InvoiceNumber" in out["helpers"]["CheckIfInvoiceNumberExists"]["where"][0]["predicate"]


CONTROLLER = '''
public class InvoiceController : Controller
{
    public ActionResult InvoiceAction(IList<InvoiceActionViewModel> list)
    {
        int statusId;
        if (list == null || list.Count <= 0)
            return RedirectToAction("Index");
        if (list[0].IsApprove)
            statusId = Svc.GetInvoiceStatusIdFromName("approved");
        else
            statusId = Svc.GetInvoiceStatusIdFromName("rejected");
        foreach (var item in list)
        {
            if (item.IsSelected)
            {
                var entity = Uow.Invoices.GetById(item.InvoiceId);
                if (entity != null)
                {
                    entity.StatusId = statusId;
                    Uow.Invoices.Update(entity);
                }
            }
        }
        return RedirectToAction("Index");
    }

    public ActionResult ChangeState(InvoiceModel model)
    {
        switch (model.InvoiceAction)
        {
            case InvoiceActionEnum.Approve:
                model.StatusId = GetInvoiceStatusId("Approved");
                break;
            case InvoiceActionEnum.Paid:
                model.StatusId = GetInvoiceStatusId("Paid");
                break;
            default:
                break;
        }
        return Ok();
    }

    public ActionResult CreateEdit(int? id)
    {
        InvoiceItemViewModel vm;
        if (id != null)
        {
            vm = Load(id);
            if (vm.IsReadOnlyState == false && vm.DueDate.Year < 1980)
                vm.DueDate = DateTime.Now;
        }
        else
        {
            vm = new InvoiceItemViewModel { StatusName = "New", DueDate = DateTime.Now.AddMonths(1), IsFromPolicy = false };
        }
        return View(vm);
    }

    public ActionResult Edit(int id)
    {
        return View(Load(id));
    }

    public ActionResult Edit(SoaModel model)
    {
        var soa = Uow.Soas.GetAll()
            .Where(s => s.ClientId == model.ClientId)
            .Where(s => s.Status.Name.ToLower() == "unpaid")
            .FirstOrDefault();
        if (soa == null)
            return HttpNotFound();
        var invoiceList = Uow.Invoices.GetAll()
            .Where(i => i.Policy.ClientId == soa.ClientId)
            .Where(i => i.IssueDate < soa.IssueDate)
            .ToList();
        if (invoiceList.Count() == 0)
            soa.StatusId = GetSoaStatusId("Paid");
        model.TotalAmountDue = invoiceList.Select(i => i.TotalAmountDue).Sum();
        return View(model);
    }
}
'''

CTL_FILE = "App/Controllers/InvoiceController.cs"
CTL = "App.Controllers.InvoiceController"


def _ctl(entry: str, line: int) -> list[str]:
    lines = CONTROLLER.splitlines()
    out = business_logic.analyse(f"{CTL}.{entry}", [{"from": f"{CTL}.{entry}", "kind": "ACCESSES_DATA",
                                                     "to": "Entities.Invoice", "file": CTL_FILE, "line": line}],
                                 lambda rel: lines if rel == CTL_FILE else [])
    return _worded(out, "invoice")


def test_a_value_held_in_a_local_variable_reaches_the_field_with_its_conditions():
    assert _ctl("InvoiceAction", 17) == [
        'if the list is not empty and the first item is marked "approve", for each item that is marked "selected" '
        'and the invoice is found, the status is set to "approved"',
        'if the list is not empty and the first item is not marked "approve", for each item that is marked '
        '"selected" and the invoice is found, the status is set to "rejected"',
        'if the list is not empty, for each item that is marked "selected" and the invoice is found, '
        "the invoice is updated"]


def test_switch_cases_object_initialisers_and_overloads():
    assert _ctl("ChangeState", 31) == ['if the invoice action is "Approve", the status is set to "Approved"',
                                       'if the invoice action is "Paid", the status is set to "Paid"']
    assert _ctl("CreateEdit", 46) == [
        'if a record is chosen and the invoice is not marked "read only state" and the due date is before 1980, '
        "the due date is set to the current date and time",
        'if no record is chosen, the status is set to "New" and the due date is set to today plus 1 month and the '
        'invoice is not marked "from policy"']


def test_query_conditions_and_aggregates_are_spelled_out():
    # Edit(int id) and Edit(SoaModel model): the overload that contains the traced line (72) is the one analysed.
    # Acronym capitals ("SOA") are applied by the story step (Ctx.fix), so the raw wording here is lower case.
    worded = _ctl("Edit", 72)
    assert len(worded) == 3
    assert worded[0] == 'if there is no soa with the same client as the invoice and status "unpaid", a "not found" page is shown'
    assert worded[1].startswith('if there is a soa with the same client as the invoice and status "unpaid" and there '
                                "are no invoices with the same client as the soa and issue date before the issue date "
                                "of the soa, the status of the soa is set to \"Paid\"")
    assert worded[2].endswith("the total amount due is set to the total of the total amount due of the invoices with "
                              "the same client as the soa and issue date before the issue date of the soa")


def test_negation_flips_the_operator_and_never_loops():
    assert ct.negate("entity.Id == 0") == "entity.Id != 0"
    assert ct.negate("a > 1 && b == null") == "(a <= 1) || (b != null)"
    assert ct.negate("x.IsOrganization") == "!x.IsOrganization"
    assert ct.negate("CreateNewInvoice(entity) == false") == "CreateNewInvoice(entity) == true"
    assert ct.describe("!(Foo(a) + Bar(b))", "invoice").startswith("it is not the case that")


def test_non_csharp_or_unparseable_input_is_left_to_the_old_checks():
    assert business_logic.analyse("Cobol.PROGRAM.MAIN", [{"from": "Cobol.PROGRAM.MAIN", "file": "MAIN.cbl", "line": 1,
                                                          "kind": "CALLS", "to": "x"}], lambda rel: ["IDENTIFICATION."]) is None
