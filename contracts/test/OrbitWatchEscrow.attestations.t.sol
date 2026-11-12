// SPDX-License-Identifier: Apache-2.0
pragma solidity 0.8.38;

import {Attestation} from "eas-contracts/Common.sol";
import {
    AttestationRequest,
    AttestationRequestData,
    MultiAttestationRequest,
    RevocationRequest,
    RevocationRequestData
} from "eas-contracts/IEAS.sol";
import {ISchemaRegistry, SchemaRecord} from "eas-contracts/ISchemaRegistry.sol";
import {ISchemaResolver} from "eas-contracts/resolver/ISchemaResolver.sol";
import {OrbitWatchEscrow} from "../src/OrbitWatchEscrow.sol";
import {EscrowTestBase} from "./helpers/EscrowTestBase.sol";

/// @notice The attestation rules (decision D-20): the two schemas, who may attest what, and
/// how each round's reviewers are chosen. Everything goes through Base Sepolia's EAS code.
contract OrbitWatchEscrowAttestationsTest is EscrowTestBase {
    // ------------------------------------------------------------------ schemas

    function test_TheSchemasAreRegisteredWithTheEscrowAsResolver() public view {
        ISchemaRegistry schemas = eas.getSchemaRegistry();
        SchemaRecord memory result = schemas.getSchema(escrow.resultSchemaUid());
        SchemaRecord memory vote = schemas.getSchema(escrow.voteSchemaUid());
        assertEq(address(result.resolver), address(escrow));
        assertEq(address(vote.resolver), address(escrow));
        assertFalse(result.revocable);
        assertFalse(vote.revocable);
        assertEq(result.schema, escrow.RESULT_SCHEMA());
        assertEq(vote.schema, escrow.VOTE_SCHEMA());
        assertEq(
            result.schema,
            "string requestId,bytes32 deliverySha256,bytes32 reportSha256,string verdict,"
            "string method,string methodVersion"
        );
        assertEq(
            vote.schema, "string requestId,bytes32 deliverySha256,bool approve,bytes32 reasonSha256"
        );
        assertEq(escrow.version(), "1.0.0");
        assertFalse(escrow.isPayable());
    }

    // ------------------------------------------------------------------ automated result

    function test_TheResultIsAPublicAttestationByTheVerifier() public {
        _fund();
        _reserveAndDeliver();
        bytes32 uid = _attestResult("pass");
        assertEq(escrow.getRequest(ID).resultAttestation, uid);
        Attestation memory a = eas.getAttestation(uid);
        assertEq(a.attester, verifier);
        assertEq(a.recipient, station);
        assertEq(a.schema, escrow.resultSchemaUid());
        assertFalse(a.revocable);
        (string memory id,, bytes32 report, string memory verdict, string memory method,) =
            abi.decode(a.data, (string, bytes32, bytes32, string, string, string));
        assertEq(id, REQUEST_ID);
        assertEq(report, REPORT);
        assertEq(verdict, "pass");
        assertEq(method, METHOD);
    }

    function test_OnlyTheVerifierAttestsResults() public {
        _fund();
        _reserveAndDeliver();
        _expectRefused(
            r1,
            _resultRequest("pass", DELIVERY, station),
            abi.encodeWithSelector(OrbitWatchEscrow.NotTheVerifier.selector, r1)
        );
        _expectRefused(
            station,
            _resultRequest("pass", DELIVERY, station),
            abi.encodeWithSelector(OrbitWatchEscrow.NotTheVerifier.selector, station)
        );
    }

    function test_AResultMustFitTheDelivery() public {
        _fund();
        vm.prank(station);
        escrow.reserve(ID);
        _expectRefused(
            verifier,
            _resultRequest("pass", DELIVERY, station),
            _wrongStatus(OrbitWatchEscrow.Status.Reserved)
        );
        vm.prank(station);
        escrow.deliver(ID, DELIVERY);

        _expectRefused(
            verifier,
            _resultRequest("pass", keccak256("other file"), station),
            abi.encodeWithSelector(OrbitWatchEscrow.WrongDelivery.selector, ID)
        );
        _expectRefused(
            verifier,
            _resultRequest("pass", DELIVERY, stranger),
            abi.encodeWithSelector(OrbitWatchEscrow.WrongRecipient.selector, stranger)
        );
        _expectRefused(
            verifier,
            _resultRequest("passed", DELIVERY, station),
            abi.encodeWithSelector(OrbitWatchEscrow.InvalidVerdict.selector)
        );

        AttestationRequest memory request = _resultRequest("pass", DELIVERY, station);
        request.data.data = abi.encode(REQUEST_ID, DELIVERY, bytes32(0), "pass", METHOD, "1");
        _expectRefused(
            verifier, request, abi.encodeWithSelector(OrbitWatchEscrow.InvalidAttestation.selector)
        );

        request = _resultRequest("pass", DELIVERY, station);
        request.data.expirationTime = uint64(vm.getBlockTimestamp() + 1 days);
        _expectRefused(
            verifier, request, abi.encodeWithSelector(OrbitWatchEscrow.InvalidAttestation.selector)
        );

        request = _resultRequest("pass", DELIVERY, station);
        request.data.data = abi.encode("SIM-REQ-9999", DELIVERY, REPORT, "pass", METHOD, "1");
        _expectRefused(
            verifier,
            request,
            abi.encodeWithSelector(
                OrbitWatchEscrow.UnknownRequest.selector, keccak256("SIM-REQ-9999")
            )
        );

        // Nothing above was recorded; the right attestation still works.
        assertEq(escrow.getRequest(ID).resultAttestation, bytes32(0));
        _attestResult("pass");
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.ChallengePeriod));
    }

    function test_AResultCanBeAttestedOnlyOnce() public {
        _toChallengePeriod("fail");
        _expectRefused(
            verifier,
            _resultRequest("pass", DELIVERY, station),
            _wrongStatus(OrbitWatchEscrow.Status.ChallengePeriod)
        );
    }

    function test_ABatchOfOneIsAnOrdinaryAttestation() public {
        _fund();
        _reserveAndDeliver();
        AttestationRequestData[] memory data = new AttestationRequestData[](1);
        data[0] = _resultRequest("inconclusive", DELIVERY, station).data;
        MultiAttestationRequest[] memory batch = new MultiAttestationRequest[](1);
        batch[0] = MultiAttestationRequest({schema: escrow.resultSchemaUid(), data: data});
        vm.prank(verifier);
        eas.multiAttest(batch);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.InReview));
    }

    // ------------------------------------------------------------------ the resolver itself

    function test_OnlyEASCallsTheResolver() public {
        Attestation memory a;
        vm.prank(stranger);
        vm.expectRevert(OrbitWatchEscrow.NotEAS.selector);
        escrow.attest(a);
        vm.prank(stranger);
        vm.expectRevert(OrbitWatchEscrow.NotEAS.selector);
        escrow.revoke(a);
        vm.prank(address(eas));
        assertFalse(escrow.revoke(a));
    }

    function test_NothingCanBeRevoked() public {
        _fund();
        _reserveAndDeliver();
        bytes32 uid = _attestResult("pass");
        RevocationRequest memory revocation = RevocationRequest({
            schema: escrow.resultSchemaUid(), data: RevocationRequestData({uid: uid, value: 0})
        });
        vm.prank(verifier);
        vm.expectRevert(bytes4(keccak256("Irrevocable()")));
        eas.revoke(revocation);

        AttestationRequest memory request = _resultRequest("pass", DELIVERY, station);
        request.data.revocable = true;
        _expectRefused(
            verifier, request, abi.encodeWithSelector(bytes4(keccak256("Irrevocable()")))
        );
    }

    function test_OtherSchemasNamingThisResolverAreRefused() public {
        // Anyone can register a schema that names the escrow as its resolver.
        vm.prank(stranger);
        bytes32 other = eas.getSchemaRegistry()
            .register("bool approve", ISchemaResolver(address(escrow)), false);
        AttestationRequest memory request = AttestationRequest({
            schema: other,
            data: AttestationRequestData({
                recipient: address(0),
                expirationTime: 0,
                revocable: false,
                refUID: bytes32(0),
                data: abi.encode(true),
                value: 0
            })
        });
        _expectRefused(
            stranger,
            request,
            abi.encodeWithSelector(OrbitWatchEscrow.UnknownSchema.selector, other)
        );
    }

    function test_PaymentsAreRefused() public {
        _fund();
        _reserveAndDeliver();
        AttestationRequest memory request = _resultRequest("pass", DELIVERY, station);
        request.data.value = 1;
        vm.deal(verifier, 1);
        vm.prank(verifier);
        vm.expectRevert(bytes4(keccak256("NotPayable()")));
        eas.attest{value: 1}(request);
    }

    // ------------------------------------------------------------------ votes

    function test_VotesComeOnlyFromTheRoundsRegisteredReviewers() public {
        address r4 = makeAddr("reviewer 4");
        address r5 = makeAddr("reviewer 5");
        registry.addReviewer(r4);
        registry.addReviewer(r5);
        _toChallengePeriod("pass");
        _expectRefused(
            r1, _voteRequest(true, REASON), _wrongStatus(OrbitWatchEscrow.Status.ChallengePeriod)
        );
        _challenge(requester);
        address[3] memory round = _round();
        address outside = _notIn(round, [r1, r2, r3, r4, r5]);

        _expectRefused(
            stranger,
            _voteRequest(true, REASON),
            abi.encodeWithSelector(OrbitWatchEscrow.NotAReviewer.selector, stranger)
        );
        _expectRefused(
            outside,
            _voteRequest(true, REASON),
            abi.encodeWithSelector(OrbitWatchEscrow.NotAssigned.selector, ID, outside)
        );
        _expectRefused(
            round[0],
            _voteRequest(true, bytes32(0)),
            abi.encodeWithSelector(OrbitWatchEscrow.MissingReason.selector)
        );

        // EAS itself refuses references to attestations that do not exist; the escrow also
        // refuses a missing reference and a reference to some other attestation.
        AttestationRequest memory request = _voteRequest(true, REASON);
        request.data.refUID = bytes32(0);
        _expectRefused(
            round[0], request, abi.encodeWithSelector(OrbitWatchEscrow.InvalidAttestation.selector)
        );
        request.data.refUID = _unrelatedAttestation();
        _expectRefused(
            round[0], request, abi.encodeWithSelector(OrbitWatchEscrow.InvalidAttestation.selector)
        );
        request = _voteRequest(true, REASON);
        request.data.data = abi.encode(REQUEST_ID, keccak256("other file"), true, REASON);
        _expectRefused(
            round[0], request, abi.encodeWithSelector(OrbitWatchEscrow.WrongDelivery.selector, ID)
        );

        bytes32 uid = _attestVote(round[0], false);
        assertEq(eas.getAttestation(uid).refUID, escrow.getRequest(ID).resultAttestation);
        _expectRefused(
            round[0],
            _voteRequest(true, REASON),
            abi.encodeWithSelector(OrbitWatchEscrow.AlreadyVoted.selector, ID, round[0])
        );
    }

    function test_ARemovedReviewersVoteNoLongerCounts() public {
        _toChallengePeriod("pass");
        _challenge(requester);
        address[3] memory round = _round();
        registry.removeReviewer(round[1]);
        _expectRefused(
            round[1],
            _voteRequest(true, REASON),
            abi.encodeWithSelector(OrbitWatchEscrow.NotAReviewer.selector, round[1])
        );
        _attestVote(round[0], true);
        _attestVote(round[2], true);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Accepted));
    }

    function test_BatchesOfSeveralAttestationsAreRefused() public {
        _toChallengePeriod("pass");
        _challenge(requester);
        address reviewer = _round()[0];
        AttestationRequestData[] memory data = new AttestationRequestData[](2);
        data[0] = _voteRequest(true, REASON).data;
        data[1] = _voteRequest(false, REASON).data;
        MultiAttestationRequest[] memory batch = new MultiAttestationRequest[](1);
        batch[0] = MultiAttestationRequest({schema: escrow.voteSchemaUid(), data: data});
        vm.prank(reviewer);
        vm.expectRevert(OrbitWatchEscrow.BatchNotSupported.selector);
        eas.multiAttest(batch);
        assertEq(escrow.getRequest(ID).voted, 0);
    }

    // ------------------------------------------------------------------ choosing reviewers

    function test_TheRoundIsTheThreeLowestScores() public {
        for (uint256 i = 4; i <= 12; ++i) {
            registry.addReviewer(makeAddr(string.concat("reviewer ", vm.toString(i))));
        }
        _toChallengePeriod("fail");
        _challenge(station);
        assertEq(_round(), _expectedRound(registry.reviewers()));
    }

    function test_PartiesAndTheirAffiliatesNeverReview() public {
        address r4 = makeAddr("reviewer 4");
        address r5 = makeAddr("reviewer 5");
        registry.addReviewer(requester);
        registry.addReviewer(station);
        registry.addReviewer(r4);
        registry.addReviewer(r5);
        registry.setAffiliation(r4, station, true); // for example the station's operator
        registry.setAffiliation(r5, requester, true); // for example the requester's employer
        _toChallengePeriod("pass");
        _challenge(requester);
        address[3] memory round = _round();
        for (uint256 i; i < 3; ++i) {
            assertTrue(round[i] == r1 || round[i] == r2 || round[i] == r3);
        }
    }

    /// @notice Even if the registry listed the parties as eligible, the escrow keeps them out.
    function test_TheEscrowItselfKeepsThePartiesOut() public {
        _toChallengePeriod("pass");
        address[] memory leaky = new address[](5);
        (leaky[0], leaky[1], leaky[2], leaky[3], leaky[4]) = (requester, station, r1, r2, r3);
        vm.mockCall(
            address(registry),
            abi.encodeWithSelector(registry.eligibleReviewers.selector, requester, station),
            abi.encode(leaky)
        );
        _challenge(requester);
        address[3] memory round = _round();
        for (uint256 i; i < 3; ++i) {
            assertTrue(round[i] != requester && round[i] != station);
        }
    }

    function test_AChallengeNeedsThreeIndependentReviewers() public {
        registry.setAffiliation(r3, station, true);
        _toChallengePeriod("pass");
        vm.prank(requester);
        vm.expectRevert(abi.encodeWithSelector(OrbitWatchEscrow.NotEnoughReviewers.selector, ID));
        escrow.challenge(ID, REASON);
        // The request stays in its challenge period, and the result stands at its end.
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.ChallengePeriod));
        skip(CHALLENGE);
        assertEq(uint8(_status()), uint8(OrbitWatchEscrow.Status.Accepted));
    }

    function test_AnInconclusiveResultNeedsThreeReviewers() public {
        registry.removeReviewer(r3);
        _fund();
        _reserveAndDeliver();
        _expectRefused(
            verifier,
            _resultRequest("inconclusive", DELIVERY, station),
            abi.encodeWithSelector(OrbitWatchEscrow.NotEnoughReviewers.selector, ID)
        );
        // Without a result the request expires, and the requester gets everything back.
        skip(VERIFICATION_TIMEOUT);
        escrow.settle(ID);
        assertEq(escrow.owed(requester), DEPOSIT);
    }

    /// @notice The contract's choice equals the published formula, for any registry.
    function testFuzz_TheRoundFollowsTheFormula(uint8 extra, uint256 seed) public {
        extra = uint8(bound(extra, 0, 40));
        for (uint256 i; i < extra; ++i) {
            registry.addReviewer(address(uint160(uint256(keccak256(abi.encode(seed, i))))));
        }
        _toChallengePeriod("pass");
        _challenge(requester);
        assertEq(_round(), _expectedRound(registry.reviewers()));
    }

    // ------------------------------------------------------------------ helpers

    /// @dev An independent implementation of the selection: sort every eligible reviewer by
    /// its score and take the first three.
    function _expectedRound(address[] memory all) internal view returns (address[3] memory) {
        uint256 n = all.length;
        uint256[] memory scores = new uint256[](n);
        for (uint256 i; i < n; ++i) {
            bool eligible = all[i] != requester && all[i] != station;
            scores[i] = eligible
                ? uint256(
                    keccak256(abi.encode("orbit-watch-reviewers/evm/1", ID, DELIVERY, all[i]))
                )
                : type(uint256).max;
        }
        for (uint256 i; i < n; ++i) {
            for (uint256 j = i + 1; j < n; ++j) {
                if (scores[j] < scores[i]) {
                    (scores[i], scores[j]) = (scores[j], scores[i]);
                    (all[i], all[j]) = (all[j], all[i]);
                }
            }
        }
        return [all[0], all[1], all[2]];
    }

    /// @dev An attestation under a schema of its own, with no resolver.
    function _unrelatedAttestation() internal returns (bytes32) {
        vm.startPrank(stranger);
        bytes32 schema =
            eas.getSchemaRegistry().register("string note", ISchemaResolver(address(0)), false);
        bytes32 uid = eas.attest(
            AttestationRequest({
                schema: schema,
                data: AttestationRequestData({
                    recipient: address(0),
                    expirationTime: 0,
                    revocable: false,
                    refUID: bytes32(0),
                    data: abi.encode("hello"),
                    value: 0
                })
            })
        );
        vm.stopPrank();
        return uid;
    }

    function _notIn(address[3] memory round, address[5] memory pool)
        internal
        pure
        returns (address)
    {
        for (uint256 i; i < pool.length; ++i) {
            if (pool[i] != round[0] && pool[i] != round[1] && pool[i] != round[2]) {
                return pool[i];
            }
        }
        revert("everyone is in the round");
    }

    function assertEq(address[3] memory a, address[3] memory b) internal pure {
        for (uint256 i; i < 3; ++i) {
            assertEq(a[i], b[i]);
        }
    }
}
